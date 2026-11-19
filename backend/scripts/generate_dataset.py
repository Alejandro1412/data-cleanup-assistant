"""Generate a customer CSV with known, injected data quality problems.

Writes three files to the output directory:

  customers_clean.csv   the data before any problem was injected
  customers_dirty.csv   the file you upload to the app
  ground_truth.json     every injected problem: row, column, category, expected fix

Usage:
    python -m scripts.generate_dataset --rows 500 --out ../sample_data
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import phonenumbers

FIRST_NAMES = [
    "James",
    "Mary",
    "Robert",
    "Patricia",
    "John",
    "Jennifer",
    "Michael",
    "Linda",
    "David",
    "Elizabeth",
    "William",
    "Barbara",
    "Richard",
    "Susan",
    "Joseph",
    "Jessica",
    "Thomas",
    "Sarah",
    "Carlos",
    "Karen",
    "Daniel",
    "Lisa",
    "Matthew",
    "Nancy",
    "Anthony",
    "Sandra",
    "Mark",
    "Ashley",
    "Steven",
    "Emily",
    "Andrew",
    "Kimberly",
    "Joshua",
    "Donna",
    "Kevin",
    "Michelle",
    "Brian",
    "Carol",
    "George",
    "Amanda",
    "Luis",
    "Melissa",
    "Diego",
    "Laura",
]
LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Sanchez",
    "Clark",
    "Ramirez",
    "Lewis",
    "Robinson",
    "Walker",
    "Young",
    "Allen",
    "King",
]
CITIES = [
    ("New York", "NY", "212"),
    ("San Francisco", "CA", "415"),
    ("Chicago", "IL", "312"),
    ("Boston", "MA", "617"),
    ("Seattle", "WA", "206"),
    ("Austin", "TX", "512"),
    ("Denver", "CO", "303"),
    ("Miami", "FL", "305"),
    ("Atlanta", "GA", "404"),
]
PLANS = [("Basic", 29.0), ("Pro", 79.0), ("Enterprise", 249.0)]
DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "proton.me"]
COLUMNS = [
    "customer_id",
    "first_name",
    "last_name",
    "email",
    "phone",
    "city",
    "state",
    "country",
    "plan",
    "signup_date",
    "birth_date",
    "monthly_spend",
    "is_active",
]


@dataclass
class Problem:
    category: str
    column: str | None
    expected: str | None = None
    # For duplicates: the customer_id of the row this one duplicates.
    duplicate_of: str | None = None


@dataclass
class Row:
    values: dict[str, str]
    problems: list[Problem] = field(default_factory=list)


def _phone(rng: random.Random, area: str) -> str:
    while True:
        number = f"+1{area}{rng.randint(200, 989)}{rng.randint(1000, 9999)}"
        if phonenumbers.is_valid_number(phonenumbers.parse(number)):
            return number


def clean_rows(rng: random.Random, count: int) -> list[Row]:
    rows = []
    used_emails: set[str] = set()
    for index in range(count):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        city, state, area = rng.choice(CITIES)
        plan, base_price = rng.choices(PLANS, weights=[5, 4, 1])[0]
        email = f"{first}.{last}{rng.randint(1, 999)}@{rng.choice(DOMAINS)}".lower()
        while email in used_emails:
            email = f"{first}.{last}{rng.randint(1, 9999)}@{rng.choice(DOMAINS)}".lower()
        used_emails.add(email)
        signup = date(2021, 1, 1) + timedelta(days=rng.randint(0, 1400))
        birth = date(1960, 1, 1) + timedelta(days=rng.randint(0, 365 * 40))
        spend = round(base_price * rng.uniform(0.9, 1.3), 2)
        rows.append(
            Row(
                {
                    "customer_id": f"C{10000 + index}",
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "phone": _phone(rng, area),
                    "city": city,
                    "state": state,
                    "country": "USA",
                    "plan": plan,
                    "signup_date": signup.isoformat(),
                    "birth_date": birth.isoformat(),
                    "monthly_spend": f"{spend:.2f}",
                    "is_active": rng.choice(["true", "true", "true", "false"]),
                }
            )
        )
    return rows


def _parse_date(value: str) -> date:
    if "/" in value:
        month, day, year = value.split("/")
        return date(int(year), int(month), int(day))
    return date.fromisoformat(value)


def _us_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{month}/{day}/{year}"


def _format_phone(e164: str, style: int) -> str:
    digits = e164[2:]
    area, exchange, line = digits[:3], digits[3:6], digits[6:]
    return [
        f"({area}) {exchange}-{line}",
        f"{area}-{exchange}-{line}",
        f"{area}.{exchange}.{line}",
    ][style]


def inject(rng: random.Random, rows: list[Row]) -> list[Row]:
    """Each injector edits a few random rows. A row gets at most one problem per
    column, so every expected fix is well defined."""
    taken: set[tuple[int, str]] = set()

    def pick(column: str, share: float) -> list[Row]:
        candidates = [i for i in range(len(rows)) if (i, column) not in taken]
        chosen = rng.sample(candidates, max(1, int(len(rows) * share)))
        taken.update((i, column) for i in chosen)
        return [rows[i] for i in chosen]

    for row in pick("first_name", 0.03):
        clean = row.values["first_name"]
        row.values["first_name"] = f" {clean}  "
        row.problems.append(Problem("whitespace", "first_name", clean))

    for row in pick("email", 0.03):
        clean = row.values["email"]
        row.values["email"] = clean.title()
        row.problems.append(Problem("email_case", "email", clean))

    for row in pick("email", 0.015):
        clean = row.values["email"]
        local, domain = clean.rsplit(".", 1)
        row.values["email"] = f"{local},{domain}"
        row.problems.append(Problem("invalid_email", "email", clean))

    for row in pick("phone", 0.3):
        clean = row.values["phone"]
        row.values["phone"] = _format_phone(clean, rng.randint(0, 2))
        row.problems.append(Problem("phone_format", "phone", clean))

    for row in pick("phone", 0.02):
        row.values["phone"] = rng.choice(["N/A", "n/a", "-"])
        row.problems.append(Problem("null_token", "phone", ""))

    for row in pick("city", 0.02):
        row.values["city"] = ""
        row.problems.append(Problem("missing", "city"))

    for row in pick("signup_date", 0.06):
        clean = row.values["signup_date"]
        row.values["signup_date"] = _us_date(clean)
        row.problems.append(Problem("date_format", "signup_date", clean))

    # "usa" and "U.S.A." are spelling variants; "United States" and "US" are
    # synonyms that need world knowledge, so only the AI pass can catch them.
    for row in pick("country", 0.06):
        variant = rng.choice(["usa", "U.S.A.", "United States", "US"])
        row.values["country"] = variant
        row.problems.append(Problem(f"category_variant:{variant}", "country", "USA"))

    for row in pick("plan", 0.03):
        clean = row.values["plan"]
        row.values["plan"] = rng.choice([clean.lower(), clean.upper()])
        row.problems.append(Problem("category_case", "plan", clean))

    for row in pick("monthly_spend", 0.02):
        clean = row.values["monthly_spend"]
        row.values["monthly_spend"] = f"${float(clean):,.2f}"
        row.problems.append(
            Problem("number_format", "monthly_spend", clean.rstrip("0").rstrip("."))
        )

    for row in pick("monthly_spend", 0.01):
        row.values["monthly_spend"] = f"{float(row.values['monthly_spend']) * 100:.2f}"
        row.problems.append(Problem("outlier", "monthly_spend"))

    for row in pick("birth_date", 0.01):
        clean = row.values["birth_date"]
        row.values["birth_date"] = "18" + clean[2:]
        row.problems.append(Problem("implausible_year", "birth_date"))

    # Born after signing up: valid in form, wrong in content. Rules cannot see this.
    for row in pick("birth_date", 0.01):
        signup = _parse_date(row.values["signup_date"])
        row.values["birth_date"] = (signup + timedelta(days=200)).isoformat()
        row.problems.append(Problem("born_after_signup", "birth_date"))

    duplicates: list[Row] = []
    for source in rng.sample(rows, max(1, int(len(rows) * 0.02))):
        copy = dict(source.values)
        copy["customer_id"] = f"C{rng.randint(90000, 99999)}"
        copy["first_name"] = copy["first_name"].upper()
        if "-" in copy["signup_date"]:
            copy["signup_date"] = _us_date(copy["signup_date"])
        duplicates.append(
            Row(copy, [Problem("exact_duplicate", None, duplicate_of=source.values["customer_id"])])
        )
    for source in rng.sample(rows, max(1, int(len(rows) * 0.02))):
        copy = dict(source.values)
        copy["customer_id"] = f"C{rng.randint(90000, 99999)}"
        name = copy["last_name"]
        position = rng.randint(1, len(name) - 2)
        copy["last_name"] = (
            name[:position] + name[position + 1] + name[position] + name[position + 2 :]
        )
        copy["city"] = ""
        duplicates.append(
            Row(copy, [Problem("near_duplicate", None, duplicate_of=source.values["customer_id"])])
        )

    combined = rows + duplicates
    rng.shuffle(combined)
    return combined


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("../sample_data"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    clean = clean_rows(rng, args.rows)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "customers_clean.csv", [dict(r.values) for r in clean])

    dirty = inject(rng, [Row(dict(r.values)) for r in clean])
    write_csv(args.out / "customers_dirty.csv", [r.values for r in dirty])

    truth: list[dict[str, Any]] = [
        {"row": index, **asdict(problem)}
        for index, row in enumerate(dirty)
        for problem in row.problems
    ]
    (args.out / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(f"Wrote {len(dirty)} rows with {len(truth)} injected problems to {args.out}")


if __name__ == "__main__":
    main()
