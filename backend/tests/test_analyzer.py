from typing import Any

from app.config import Settings
from app.domain.models import Action, IssueKind, Source, Suggestion
from app.llm.base import LLMError
from app.llm.reviewer import AIReviewer
from app.pipeline.analyzer import Analyzer, merge_suggestions
from tests.helpers import FakeProvider, frame_from

PEOPLE = frame_from(
    [
        {"name": "Ana Ruiz", "country": "USA", "email": "ana@x.com", "age": "34"},
        {"name": "Luis Gil", "country": "United States", "email": "luis@x.com", "age": "41"},
        {"name": "Eva Diaz", "country": "USA", "email": "eva@x.com", "age": "29"},
        {"name": "Ana Ruis", "country": "USA", "email": "ana@x.com", "age": "34"},
        {"name": "Tom Hall", "country": "Mexico", "email": "tom@x.com", "age": "7"},
        {"name": "Kim Park", "country": "Mexico", "email": "kim@x.com", "age": "38"},
    ]
)


def _analyze(provider: FakeProvider | None) -> tuple[list[Suggestion], list[str]]:
    reviewer = AIReviewer(provider) if provider else None
    result = Analyzer(Settings(anthropic_api_key=None), reviewer).run(PEOPLE)
    return result.suggestions, result.warnings


def test_rules_only_run_reports_that_ai_is_off() -> None:
    suggestions, warnings = _analyze(None)

    assert any(s.kind is IssueKind.NEAR_DUPLICATE for s in suggestions)
    assert all(s.source is Source.RULE for s in suggestions)
    assert "AI review is off" in warnings[0]


def test_ai_category_mapping_handles_synonyms_rules_cannot_see() -> None:
    provider = FakeProvider(
        {
            "category_changes": {
                "changes": [
                    {
                        "value": "United States",
                        "canonical": "USA",
                        "confidence": 0.93,
                        "reason": "Same country.",
                    },
                ]
            },
        }
    )

    suggestions, _ = _analyze(provider)

    [change] = [s for s in suggestions if s.kind is IssueKind.INCONSISTENT_CATEGORY]
    assert (change.row_index, change.proposed_value, change.source) == (1, "USA", Source.AI)


def test_ai_results_referring_to_unknown_data_are_dropped() -> None:
    provider = FakeProvider(
        {
            "category_changes": {
                "changes": [
                    {"value": "Atlantis", "canonical": "USA", "confidence": 0.9, "reason": "x"},
                ]
            },
            "record_issues": {
                "issues": [
                    {"row": 999, "column": "age", "problem": "x", "confidence": 0.9},
                    {"row": 1, "column": "no_such_column", "problem": "x", "confidence": 0.9},
                ]
            },
        }
    )

    suggestions, _ = _analyze(provider)

    assert not any(s.kind is IssueKind.INCONSISTENT_CATEGORY for s in suggestions)
    assert not any(s.kind is IssueKind.SUSPICIOUS_RECORD for s in suggestions)


def test_ai_can_confirm_or_dismiss_duplicates() -> None:
    def dismiss(_: str) -> dict[str, Any]:
        return {
            "decisions": [
                {"pair_id": "p0", "is_duplicate": False, "confidence": 0.9, "reason": "Different."},
            ]
        }

    def confirm(_: str) -> dict[str, Any]:
        return {
            "decisions": [
                {
                    "pair_id": "p0",
                    "is_duplicate": True,
                    "confidence": 0.97,
                    "reason": "Typo in name.",
                },
            ]
        }

    dismissed, _ = _analyze(FakeProvider({"duplicate_decisions": dismiss}))
    confirmed, _ = _analyze(FakeProvider({"duplicate_decisions": confirm}))

    assert not any(s.kind is IssueKind.NEAR_DUPLICATE for s in dismissed)
    [duplicate] = [s for s in confirmed if s.kind is IssueKind.NEAR_DUPLICATE]
    assert duplicate.source is Source.AI
    assert duplicate.confidence == 0.97


def test_ai_record_review_adds_suspicious_records() -> None:
    provider = FakeProvider(
        {
            "record_issues": {
                "issues": [
                    {
                        "row": 5,
                        "column": "age",
                        "problem": "Age 7 is unlikely for a customer account.",
                        "proposed_value": None,
                        "confidence": 0.7,
                    },
                ]
            },
        }
    )

    suggestions, _ = _analyze(provider)

    [issue] = [s for s in suggestions if s.kind is IssueKind.SUSPICIOUS_RECORD]
    assert (issue.row_index, issue.column, issue.action) == (4, "age", Action.FLAG)


def test_a_failing_ai_pass_is_skipped_and_reported() -> None:
    provider = FakeProvider({"duplicate_decisions": LLMError("timeout")})

    suggestions, warnings = _analyze(provider)

    assert any("duplicates was skipped: timeout" in w for w in warnings)
    [duplicate] = [s for s in suggestions if s.kind is IssueKind.NEAR_DUPLICATE]
    assert duplicate.source is Source.RULE


def test_prompts_never_include_rows_beyond_the_configured_sample() -> None:
    provider = FakeProvider({})
    big = frame_from([{"name": f"Person {i}", "score": str(i % 7)} for i in range(500)])
    settings = Settings(anthropic_api_key=None, llm_max_review_rows=20)

    Analyzer(settings, AIReviewer(provider)).run(big)

    [prompt] = provider.prompts["record_issues"]
    assert prompt.count('"row":') == 20


def test_merge_keeps_one_value_change_per_cell_and_all_flags() -> None:
    def make(action: Action, proposed: str | None, kind: IssueKind) -> Suggestion:
        return Suggestion(
            kind=kind,
            action=action,
            row_index=0,
            column="c",
            current_value=" x ",
            proposed_value=proposed,
            reason="",
            confidence=0.9,
            source=Source.RULE,
            group_key="g",
        )

    merged = merge_suggestions(
        [
            make(Action.SET_VALUE, "x", IssueKind.INCONSISTENT_FORMAT),
            make(Action.SET_VALUE, "X", IssueKind.INCONSISTENT_CATEGORY),
            make(Action.FLAG, None, IssueKind.OUTLIER),
        ]
    )

    assert [(s.action, s.proposed_value) for s in merged] == [
        (Action.SET_VALUE, "X"),
        (Action.FLAG, None),
    ]
