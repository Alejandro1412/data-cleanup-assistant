from __future__ import annotations

from app.detectors.base import DetectionContext
from app.domain.models import Action, ColumnType, IssueKind, Source, Suggestion
from app.pipeline import values as v

# Above this share of empty cells a column is "optional", and flagging every
# empty cell would bury the useful findings. The profile still reports it.
MAX_NULL_RATIO_TO_FLAG = 0.5

# These usually mean "no value", but in a categorical column "Unknown" can be a
# deliberate answer, so they get a lower confidence than "N/A" or "null".
SOFT_NULL_TOKENS = frozenset({"none", "unknown", "missing", "undefined", "?"})


class MissingValueDetector:
    name = "missing_values"
    stage = 10

    def detect(self, context: DetectionContext) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for column, profile in context.profiles.items():
            if profile.inferred_type is ColumnType.EMPTY:
                continue
            flag_empty_cells = profile.null_ratio <= MAX_NULL_RATIO_TO_FLAG
            filled_pct = round((1 - profile.null_ratio) * 100)

            for row, value in context.cells(column):
                if v.is_null_token(value):
                    soft = value.strip().lower() in SOFT_NULL_TOKENS
                    suggestions.append(
                        Suggestion(
                            kind=IssueKind.MISSING_VALUE,
                            action=Action.SET_VALUE,
                            row_index=row,
                            column=column,
                            current_value=value,
                            proposed_value="",
                            reason=f'"{value}" is a placeholder for a missing value. '
                            "Storing it as an empty cell keeps missing data consistent.",
                            confidence=0.75 if soft else 0.95,
                            source=Source.RULE,
                            group_key=f"null_token:{column}:{value.strip().lower()}",
                        )
                    )
                elif value.strip() == "" and flag_empty_cells:
                    suggestions.append(
                        Suggestion(
                            kind=IssueKind.MISSING_VALUE,
                            action=Action.FLAG,
                            row_index=row,
                            column=column,
                            current_value=value,
                            reason=f"No value for {column}. {filled_pct}% of rows have one.",
                            confidence=1.0,
                            source=Source.RULE,
                            group_key=f"missing:{column}",
                        )
                    )
        return suggestions
