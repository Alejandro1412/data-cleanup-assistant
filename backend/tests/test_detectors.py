from app.detectors.categories import CategoryDetector
from app.detectors.duplicates import DuplicateDetector
from app.detectors.formats import FormatDetector
from app.detectors.missing import MissingValueDetector
from app.detectors.outliers import OutlierDetector
from app.domain.models import Action, IssueKind
from tests.helpers import context_for, frame_from


def _changes(suggestions: list, kind: IssueKind | None = None) -> dict[tuple[int, str], str]:
    return {
        (s.row_index, s.column): s.proposed_value
        for s in suggestions
        if s.action is Action.SET_VALUE and (kind is None or s.kind is kind)
    }


class TestMissingValues:
    def test_replaces_placeholders_and_flags_empty_cells(self) -> None:
        frame = frame_from([{"city": c} for c in ["Cali", "N/A", "", "Pasto", "Cali"]])

        found = MissingValueDetector().detect(context_for(frame))

        assert _changes(found) == {(1, "city"): ""}
        assert [(s.row_index, s.action) for s in found if s.action is Action.FLAG] == [
            (2, Action.FLAG)
        ]

    def test_does_not_flag_every_cell_of_a_mostly_empty_column(self) -> None:
        frame = frame_from([{"note": n} for n in ["", "", "", "x"]])

        found = MissingValueDetector().detect(context_for(frame))

        assert found == []


class TestFormats:
    def test_trims_whitespace_in_text(self) -> None:
        frame = frame_from([{"name": n} for n in ["Ana  Ruiz ", "Luis", "Eva"]])

        assert _changes(FormatDetector().detect(context_for(frame))) == {(0, "name"): "Ana Ruiz"}

    def test_normalizes_mixed_date_formats_to_iso(self) -> None:
        frame = frame_from([{"d": d} for d in ["2024-01-05", "25/12/2024", "2024-02-01"]])

        changes = _changes(FormatDetector().detect(context_for(frame)))

        assert changes == {(1, "d"): "2024-12-25"}

    def test_leaves_consistent_dates_alone(self) -> None:
        frame = frame_from([{"d": d} for d in ["01/05/2024", "02/06/2024", "03/07/2024"]])

        assert FormatDetector().detect(context_for(frame)) == []

    def test_marks_day_month_ambiguity_with_low_confidence(self) -> None:
        frame = frame_from([{"d": d} for d in ["2024-01-05", "03/04/2024", "2024-02-01"]])

        [suggestion] = FormatDetector().detect(context_for(frame))

        assert suggestion.confidence < 0.7
        assert "swapped" in suggestion.reason

    def test_lowercases_and_repairs_emails(self) -> None:
        emails = ["Ana@Mail.com", "luis@mail,com", "not an email at all", "eva@mail.com"]
        frame = frame_from([{"email": e} for e in emails])

        found = FormatDetector().detect(context_for(frame))

        assert _changes(found) == {(0, "email"): "ana@mail.com", (1, "email"): "luis@mail.com"}
        assert [s.row_index for s in found if s.action is Action.FLAG] == [2]

    def test_converts_mixed_phone_formats_to_e164(self) -> None:
        phones = ["(415) 555-0100", "415.555.0101", "+14155550102"]
        frame = frame_from([{"phone": p} for p in phones])

        changes = _changes(FormatDetector().detect(context_for(frame)))

        assert changes == {(0, "phone"): "+14155550100", (1, "phone"): "+14155550101"}

    def test_skips_phone_validation_when_most_numbers_fail(self) -> None:
        frame = frame_from([{"phone": p} for p in ["555-0100", "555-0101", "555-0102"]])

        assert FormatDetector().detect(context_for(frame)) == []

    def test_strips_currency_and_separators_from_numbers(self) -> None:
        frame = frame_from([{"amount": a} for a in ["10", "$1,200.50", "7", "abc", "8"]])

        found = FormatDetector().detect(context_for(frame))

        assert _changes(found) == {(1, "amount"): "1200.5"}
        assert [s.row_index for s in found if s.kind is IssueKind.INVALID_VALUE] == [3]

    def test_unifies_boolean_spelling(self) -> None:
        frame = frame_from([{"active": a} for a in ["yes", "no", "yes", "Y", "false"]])

        changes = _changes(FormatDetector().detect(context_for(frame)))

        assert changes == {(3, "active"): "yes", (4, "active"): "no"}


class TestCategories:
    def test_maps_case_punctuation_and_typo_variants_to_the_common_value(self) -> None:
        values = (
            ["USA"] * 20
            + ["usa", "U.S.A.", "Canada", "Canada", "Mexico", "Mexco"]
            + ["Mexico"] * 10
        )
        frame = frame_from([{"country": c} for c in values])

        changes = _changes(CategoryDetector().detect(context_for(frame)))

        assert changes == {
            (20, "country"): "USA",
            (21, "country"): "USA",
            (25, "country"): "Mexico",
        }

    def test_does_not_merge_two_large_similar_categories(self) -> None:
        values = ["Austria"] * 10 + ["Australia"] * 10 + ["Peru"] * 5
        frame = frame_from([{"country": c} for c in values])

        assert CategoryDetector().detect(context_for(frame)) == []


class TestOutliers:
    def test_flags_extreme_values_using_median_and_mad(self) -> None:
        amounts = ["100", "102", "98", "101", "99", "103", "97", "100", "5000"]
        frame = frame_from([{"amount": a} for a in amounts])

        found = OutlierDetector().detect(context_for(frame))

        assert [(s.row_index, s.kind) for s in found] == [(8, IssueKind.OUTLIER)]

    def test_values_normal_for_their_group_are_not_outliers(self) -> None:
        rows = [{"plan": "Basic", "price": str(30 + i % 5)} for i in range(40)]
        rows += [{"plan": "Enterprise", "price": str(250 + i % 9)} for i in range(10)]
        rows.append({"plan": "Basic", "price": "3100"})
        frame = frame_from(rows)

        found = OutlierDetector().detect(context_for(frame))

        assert [s.row_index for s in found] == [50]

    def test_flags_implausible_years(self) -> None:
        dates = ["2020-01-01", "1850-06-01", "2021-03-03", "2099-01-01"]
        frame = frame_from([{"born": d} for d in dates])

        found = OutlierDetector().detect(context_for(frame))

        assert sorted(s.row_index for s in found) == [1, 3]


class TestDuplicates:
    def test_finds_rows_that_differ_only_in_formatting(self) -> None:
        frame = frame_from(
            [
                {"id": "1", "name": "Ana Ruiz", "email": "ana@x.com", "joined": "2024-01-05"},
                {"id": "2", "name": "Luis Gil", "email": "luis@x.com", "joined": "2024-02-01"},
                {"id": "3", "name": "ANA RUIZ ", "email": "Ana@X.com", "joined": "01/05/2024"},
            ]
        )

        [found] = DuplicateDetector().detect(context_for(frame))

        assert found.kind is IssueKind.EXACT_DUPLICATE
        assert (found.row_index, found.related_row_index) == (2, 0)

    def test_finds_near_duplicates_and_keeps_the_more_complete_row(self) -> None:
        frame = frame_from(
            [
                {"name": "Jonathan Smith", "email": "jsmith@acme.com", "city": ""},
                {"name": "Maria Lopez", "email": "mlopez@acme.com", "city": "Austin"},
                {"name": "Jonathon Smith", "email": "jsmith@acme.com", "city": "Denver"},
            ]
        )

        [found] = DuplicateDetector().detect(context_for(frame))

        assert found.kind is IssueKind.NEAR_DUPLICATE
        assert (found.row_index, found.related_row_index) == (0, 2)
        assert "Jonathan Smith" in found.reason

    def test_ignores_different_people_with_shared_details(self) -> None:
        frame = frame_from(
            [
                {"name": "Ana Ruiz", "email": "ana@x.com", "city": "Austin"},
                {"name": "Luis Gil", "email": "luis@x.com", "city": "Austin"},
            ]
        )

        assert DuplicateDetector().detect(context_for(frame)) == []
