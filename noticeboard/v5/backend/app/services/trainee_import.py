"""Bulk trainee import from CSV: parse, then validate every row against the database before anything
is written. The same validation runs for the preview (dry run) and again for the real import."""

import csv
import io

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Cohort, User

REQUIRED_COLUMNS = ("name", "email", "cohort_id")
MAX_ROWS = 500
_email = TypeAdapter(EmailStr)


class CsvFormatError(ValueError):
    """The file as a whole can't be used (no header, missing columns, too many rows...)."""


def parse_and_validate(db: Session, text: str) -> list[dict]:
    """One dict per data row: {line, name, email, cohort_id, errors}. A row with no errors is importable."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))  # Excel adds a byte-order mark
    if not reader.fieldnames:
        raise CsvFormatError("The file is empty")
    reader.fieldnames = [(name or "").strip().lower() for name in reader.fieldnames]
    missing = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing:
        raise CsvFormatError(f"Missing column(s): {', '.join(missing)}. The header row must be: name,email,cohort_id")

    rows = []
    for record in reader:
        if not any((value or "").strip() for value in record.values() if isinstance(value, str)):
            continue  # skip blank lines
        rows.append(
            {
                "line": reader.line_num,  # file line, header = 1 (handles quoted multi-line fields)
                "name": (record.get("name") or "").strip(),
                "email": (record.get("email") or "").strip().lower(),
                "cohort_id": (record.get("cohort_id") or "").strip() or None,
                "errors": [],
            }
        )
    if not rows:
        raise CsvFormatError("The file has a header but no data rows")
    if len(rows) > MAX_ROWS:
        raise CsvFormatError(f"Too many rows ({len(rows)}); import at most {MAX_ROWS} at a time")

    # Two queries for the whole file, not one per row.
    emails = {row["email"] for row in rows if row["email"]}
    taken = set(db.scalars(select(func.lower(User.email)).where(func.lower(User.email).in_(emails))))
    cohorts = set(db.scalars(select(Cohort.id)))

    first_line_for: dict[str, int] = {}
    for row in rows:
        errors = row["errors"]
        if not row["name"]:
            errors.append("Name is required")
        elif len(row["name"]) > 100:
            errors.append("Name is longer than 100 characters")

        if not row["email"]:
            errors.append("Email is required")
        else:
            try:
                _email.validate_python(row["email"])
            except ValidationError:
                errors.append("Not a valid email address")
            else:
                if row["email"] in taken:
                    errors.append("Already has an account")
                elif row["email"] in first_line_for:
                    errors.append(f"Same email as line {first_line_for[row['email']]}")
            first_line_for.setdefault(row["email"], row["line"])

        if row["cohort_id"] is not None and row["cohort_id"] not in cohorts:
            errors.append(f"No cohort '{row['cohort_id']}'")
    return rows
