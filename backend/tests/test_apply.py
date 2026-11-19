from app.domain.models import Action, IssueKind, Source, Status, Suggestion
from app.pipeline.apply import apply_suggestions
from tests.helpers import frame_from

ORIGINAL = frame_from(
    [
        {"name": "Ana ", "city": "N/A"},
        {"name": "Luis", "city": "Cali"},
        {"name": "Ana", "city": ""},
    ]
)


def _suggestion(
    action: Action,
    row: int,
    column: str | None = None,
    proposed: str | None = None,
    status: Status = Status.ACCEPTED,
    final: str | None = None,
) -> Suggestion:
    return Suggestion(
        id=f"{action.value}-{row}-{column}",
        kind=IssueKind.INCONSISTENT_FORMAT,
        action=action,
        row_index=row,
        column=column,
        proposed_value=proposed,
        reason="r",
        confidence=0.9,
        source=Source.RULE,
        group_key="g",
        status=status,
        final_value=final,
    )


def test_applies_only_accepted_suggestions_and_never_touches_the_original() -> None:
    cleaned, audit = apply_suggestions(
        ORIGINAL,
        [
            _suggestion(Action.SET_VALUE, 0, "name", "Ana"),
            _suggestion(Action.SET_VALUE, 0, "city", "", status=Status.REJECTED),
            _suggestion(Action.DROP_ROW, 2),
        ],
    )

    assert cleaned.to_dict("records") == [
        {"name": "Ana", "city": "N/A"},
        {"name": "Luis", "city": "Cali"},
    ]
    assert ORIGINAL.at[0, "name"] == "Ana "
    assert [(e.row, e.action, e.before, e.after) for e in audit] == [
        (1, "set_value", "Ana ", "Ana"),
        (3, "drop_row", "", ""),
    ]


def test_reviewer_value_overrides_proposal_and_fills_flagged_cells() -> None:
    cleaned, audit = apply_suggestions(
        ORIGINAL,
        [
            _suggestion(Action.SET_VALUE, 1, "city", "CALI", final="Cali, CO"),
            _suggestion(Action.FLAG, 2, "city", final="Bogotá"),
            _suggestion(Action.FLAG, 0, "city"),
        ],
    )

    assert cleaned["city"].tolist() == ["N/A", "Cali, CO", "Bogotá"]
    assert len(audit) == 2
