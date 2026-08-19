import json
from dataclasses import dataclass, field
from pathlib import Path

from vibeproof.analyst import AnalystPolicy, CitationReviewer, RepositoryAnalystAgent
from vibeproof.evidence_store import EvidenceStore
from vibeproof.model_client import ModelClientError, ModelMessage
from vibeproof.reporting import render_architecture_report
from vibeproof.scanner import RepositoryScanner
from vibeproof.schemas import AgentRunStatus, ClaimDraft, ClaimStatus, VerificationStatus
from vibeproof.source_index import PythonSourceIndexer

SOURCE = """from fastapi import APIRouter

router = APIRouter()


class DemoService:
    async def execute(self, value: str) -> str:
        return value


@router.post("/run")
async def run_demo(service: DemoService) -> str:
    return await service.execute("ready")
"""


@dataclass
class ScriptedModel:
    responses: list[str]
    provider: str = "scripted"
    model: str = "scripted-v1"
    received: list[list[ModelMessage]] = field(default_factory=list)

    def complete(self, messages: list[ModelMessage]) -> str:
        self.received.append(messages)
        if not self.responses:
            raise ModelClientError("no scripted response")
        return self.responses.pop(0)


class FailingModel:
    provider = "failing"
    model = "failing-v1"

    def complete(self, messages: list[ModelMessage]) -> str:
        raise ModelClientError("provider unavailable")


def _repository(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "main.py").write_text(SOURCE, encoding="utf-8")
    manifest = RepositoryScanner().scan(repository)
    indexed = PythonSourceIndexer().build(repository, manifest)
    store = EvidenceStore(tmp_path / "index.sqlite3")
    store.replace_snapshot(manifest.repository_name, manifest.snapshot_id, indexed)
    return repository, manifest, store


def _final_action(chunk_id: str, claim: str = "run_demo delegates work to DemoService.execute.") -> str:
    return json.dumps(
        {
            "action": "FINAL_ANSWER",
            "summary": "The repository exposes one routed service operation.",
            "claims": [
                {
                    "claim": claim,
                    "claim_type": "DATA_FLOW",
                    "evidence_ids": [chunk_id],
                    "confidence": 0.9,
                }
            ],
            "unresolved_questions": ["Runtime behavior has not been executed."],
        }
    )


def test_agent_searches_then_accepts_observed_citation(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    hit = store.search(manifest.snapshot_id, "run_demo", limit=1)[0]
    model = ScriptedModel(
        responses=[
            json.dumps({"action": "SEARCH_SOURCE", "query": "run_demo"}),
            _final_action(hit.chunk_id),
        ]
    )

    report = RepositoryAnalystAgent(store, model).run(manifest)

    assert report.run_status == AgentRunStatus.COMPLETED
    assert report.verification_status == VerificationStatus.VERIFIED
    assert len(report.claims) == 1
    assert report.claims[0].status == ClaimStatus.SOURCE_SUPPORTED
    assert report.evidence[0].chunk_id == hit.chunk_id
    assert [step.action for step in report.trace] == ["SEARCH_SOURCE", "FINAL_ANSWER"]
    assert "untrusted data" in model.received[0][0].content


def test_unobserved_existing_chunk_is_rejected(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    hit = store.search(manifest.snapshot_id, "run_demo", limit=1)[0]
    model = ScriptedModel(responses=[_final_action(hit.chunk_id)])

    report = RepositoryAnalystAgent(store, model).run(manifest)

    assert report.claims == []
    assert report.rejected_claims[0].status == ClaimStatus.REJECTED
    assert "not returned to the agent" in report.rejected_claims[0].rejection_reason
    assert report.verification_status == VerificationStatus.DEGRADED


def test_claim_without_evidence_is_unsupported(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    action = json.dumps(
        {
            "action": "FINAL_ANSWER",
            "summary": "Unsupported result",
            "claims": [{"claim": "The service is always reliable.", "claim_type": "RISK"}],
        }
    )

    report = RepositoryAnalystAgent(store, ScriptedModel([action])).run(manifest)

    assert report.rejected_claims[0].status == ClaimStatus.UNSUPPORTED
    assert report.evidence == []


def test_reviewer_rejects_stale_evidence(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    hit = store.search(manifest.snapshot_id, "run_demo", limit=1)[0]
    stale = hit.model_copy(update={"snapshot_id": "sha256:stale"})
    draft = ClaimDraft(claim="A stale claim.", evidence_ids=[hit.chunk_id])

    result = CitationReviewer(store).review([draft], {hit.chunk_id: stale}, manifest.snapshot_id)

    assert result.accepted == ()
    assert result.rejected[0].status == ClaimStatus.STALE_EVIDENCE


def test_reviewer_rejects_tampered_evidence_metadata(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    hit = store.search(manifest.snapshot_id, "run_demo", limit=1)[0]
    tampered = hit.model_copy(update={"path": "invented.py"})
    draft = ClaimDraft(claim="A tampered claim.", evidence_ids=[hit.chunk_id])

    result = CitationReviewer(store).review([draft], {hit.chunk_id: tampered}, manifest.snapshot_id)

    assert result.rejected[0].status == ClaimStatus.REJECTED
    assert "integrity review" in result.rejected[0].rejection_reason


def test_invalid_or_unknown_actions_stop_safely(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    model = ScriptedModel(
        responses=[
            "not-json",
            json.dumps({"action": "DELETE_FILES", "path": "/"}),
        ]
    )

    report = RepositoryAnalystAgent(store, model).run(manifest)

    assert report.run_status == AgentRunStatus.INVALID_ACTION
    assert report.verification_status == VerificationStatus.FAILED
    assert [step.action for step in report.trace] == ["INVALID_ACTION", "INVALID_ACTION"]
    assert all("DELETE_FILES" not in (step.message or "") for step in report.trace)


def test_duplicate_query_is_rejected(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    search = json.dumps({"action": "SEARCH_SOURCE", "query": "run_demo"})
    model = ScriptedModel(responses=[search, search])
    policy = AnalystPolicy(max_invalid_actions=1)

    report = RepositoryAnalystAgent(store, model, policy).run(manifest)

    assert report.run_status == AgentRunStatus.INVALID_ACTION
    assert report.trace[-1].error == "duplicate query"


def test_agent_returns_max_steps_report(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    model = ScriptedModel(
        responses=[
            json.dumps({"action": "SEARCH_SOURCE", "query": "run_demo"}),
            json.dumps({"action": "SEARCH_SOURCE", "query": "DemoService"}),
        ]
    )

    report = RepositoryAnalystAgent(store, model, AnalystPolicy(max_steps=2)).run(manifest)

    assert report.run_status == AgentRunStatus.MAX_STEPS
    assert len(report.trace) == 2


def test_agent_converts_provider_failure_to_auditable_report(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)

    report = RepositoryAnalystAgent(store, FailingModel()).run(manifest)

    assert report.run_status == AgentRunStatus.MODEL_ERROR
    assert report.trace[0].error == "provider unavailable"
    assert report.warnings == ["provider unavailable"]


def test_markdown_report_contains_citations_but_not_source_excerpts(tmp_path: Path) -> None:
    _, manifest, store = _repository(tmp_path)
    hit = store.search(manifest.snapshot_id, "run_demo", limit=1)[0]
    model = ScriptedModel([json.dumps({"action": "SEARCH_SOURCE", "query": "run_demo"}), _final_action(hit.chunk_id)])
    report = RepositoryAnalystAgent(store, model).run(manifest)

    rendered = render_architecture_report(report)

    assert f"main.py:{hit.start_line}-{hit.end_line}" in rendered
    assert hit.chunk_id in rendered
    assert "return await service.execute" not in rendered
