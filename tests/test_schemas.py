import pytest
from pydantic import ValidationError

from vibeproof.schemas import Evidence, EvidenceKind, VerificationStatus


def test_source_evidence_requires_a_path() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.SOURCE,
            status=VerificationStatus.VERIFIED,
            claim="The API entry point exists.",
            created_by="test",
        )


def test_runtime_evidence_requires_tokenized_command() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.RUNTIME,
            status=VerificationStatus.VERIFIED,
            claim="Tests passed.",
            created_by="test",
        )


def test_line_range_must_be_ordered() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            kind=EvidenceKind.SOURCE,
            status=VerificationStatus.VERIFIED,
            claim="The route calls the service.",
            source_path="app/api.py",
            start_line=20,
            end_line=10,
            created_by="test",
        )
