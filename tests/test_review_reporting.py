from __future__ import annotations

from pathlib import Path

from test_answer_reviewer import _context

from vibeproof.answer_reviewer import AnswerReviewAgent
from vibeproof.model_client import MockAnswerReviewModelClient
from vibeproof.review_reporting import render_answer_review


def test_markdown_review_exposes_progress_and_limitations(tmp_path: Path) -> None:
    takeover, submission, store = _context(tmp_path)
    submission.answers[0].answer = "A structurally valid answer."
    review = AnswerReviewAgent(store, MockAnswerReviewModelClient()).run(takeover, submission)

    rendered = render_answer_review(review, takeover)

    assert "# Learning review" in rendered
    assert "Review mode: `STRUCTURE_ONLY`" in rendered
    assert "## Progress" in rendered
    assert "not scored" in rendered
    assert takeover.learning_plan.questions[0].prompt in rendered
