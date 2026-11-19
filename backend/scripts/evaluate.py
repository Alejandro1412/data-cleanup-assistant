"""Measure detection quality against the generated ground truth.

For every injected problem we check whether the analysis produced a suggestion
on the same row and column (or a row drop, for duplicates), and whether the
proposed value equals the expected fix. Every other suggestion counts as a
false positive.

Usage:
    python -m scripts.evaluate --data ../sample_data
Set ANTHROPIC_API_KEY to include the AI passes.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.dependencies import build_reviewer
from app.domain.models import Action, Suggestion
from app.pipeline.analyzer import Analyzer
from app.pipeline.ingest import load_csv
from app.storage.repository import Repository


def _matches(problem: dict[str, Any], suggestion: Suggestion, ids: dict[int, str]) -> bool:
    if problem["column"] is None:
        if suggestion.action is not Action.DROP_ROW:
            return False
        pair = {suggestion.row_index, suggestion.related_row_index}
        source = next((row for row, cid in ids.items() if cid == problem["duplicate_of"]), None)
        return pair == {problem["row"], source}
    return suggestion.row_index == problem["row"] and suggestion.column == problem["column"]


def evaluate(data_dir: Path) -> dict[str, Any]:
    settings = get_settings()
    frame = load_csv((data_dir / "customers_dirty.csv").read_bytes(), settings.max_rows).frame
    truth: list[dict[str, Any]] = json.loads((data_dir / "ground_truth.json").read_text())
    ids = {i: str(cid) for i, cid in enumerate(frame["customer_id"])}

    reviewer = build_reviewer(settings, Repository(settings.database_path))
    result = Analyzer(settings, reviewer).run(frame)
    suggestions = result.suggestions
    duplicate_rows = {p["row"] for p in truth if p["column"] is None}

    used: set[str] = set()
    per_category: dict[str, dict[str, int]] = defaultdict(
        lambda: {"injected": 0, "found": 0, "correct_fix": 0}
    )
    for problem in truth:
        category = problem["category"].split(":")[0]
        stats = per_category[category]
        stats["injected"] += 1
        match = next((s for s in suggestions if _matches(problem, s, ids)), None)
        if match is None:
            continue
        used.add(match.id)
        stats["found"] += 1
        if problem.get("expected") is not None and match.proposed_value == problem["expected"]:
            stats["correct_fix"] += 1

    # Suggestions on rows that are themselves injected duplicates are not
    # counted against precision: the row is going to be dropped anyway.
    unmatched = [s for s in suggestions if s.id not in used and s.row_index not in duplicate_rows]
    found = sum(c["found"] for c in per_category.values())
    return {
        "ai_model": reviewer.model if reviewer else None,
        "rows": len(frame),
        "injected": len(truth),
        "suggestions": len(suggestions),
        "recall": round(found / len(truth), 3),
        "precision": round(found / (found + len(unmatched)), 3) if suggestions else 0.0,
        "per_category": dict(sorted(per_category.items())),
        "false_positives_by_kind": _count_by_kind(unmatched),
        "warnings": result.warnings,
    }


def _count_by_kind(suggestions: list[Suggestion]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for s in suggestions:
        counts[f"{s.kind.value}:{s.column or 'row'}"] += 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data", type=Path, default=Path("../sample_data"))
    args = parser.parse_args()
    report = evaluate(args.data)

    print(f"Model: {report['ai_model'] or 'none (rules only)'}")
    print(
        f"Rows: {report['rows']}  Injected problems: {report['injected']}  "
        f"Suggestions: {report['suggestions']}"
    )
    print(f"Recall: {report['recall']:.1%}  Precision: {report['precision']:.1%}\n")
    print(f"{'category':<22}{'injected':>9}{'found':>8}{'recall':>9}{'fix ok':>9}")
    for category, stats in report["per_category"].items():
        recall = stats["found"] / stats["injected"]
        print(
            f"{category:<22}{stats['injected']:>9}{stats['found']:>8}{recall:>9.0%}"
            f"{stats['correct_fix']:>9}"
        )
    if report["false_positives_by_kind"]:
        print("\nUnmatched suggestions:")
        for kind, count in report["false_positives_by_kind"].items():
            print(f"  {kind}: {count}")
    for warning in report["warnings"]:
        print(f"\nNote: {warning}")


if __name__ == "__main__":
    main()
