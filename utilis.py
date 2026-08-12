"""
utilis.py
Small shared helper functions used across the app: CSV I/O, email
validation, and de-duplication.
"""

import csv
import os
import re

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp")


def is_valid_email(value):
    """Regex-based syntax validation, per the spec's Email Validation
    Module: reject malformed addresses, image filenames mistakenly
    captured as emails, and unreasonably long domains."""
    if not value:
        return False
    value = value.strip().strip(".,;:()[]<>\"'")
    if not value or len(value) > 254:
        return False
    if value.lower().endswith(IMAGE_EXTENSIONS):
        return False
    local, _, domain = value.partition("@")
    if not local or not domain or len(domain) > 50:
        return False
    return bool(EMAIL_PATTERN.match(value))


def _read_csv_rows(csv_path):
    """Read a CSV's first-column values, tolerating non-UTF-8 files
    instead of crashing the whole upload."""
    if not os.path.exists(csv_path):
        return []
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            return [row[0].strip() for row in csv.reader(f) if row and row[0].strip()]
    except UnicodeDecodeError:
        with open(csv_path, "r", newline="", encoding="latin-1", errors="replace") as f:
            return [row[0].strip() for row in csv.reader(f) if row and row[0].strip()]


def read_and_validate(csv_path):
    """
    Read a single-column CSV of email addresses and split it into
    (valid_emails, invalid_values) — de-duplicated case-insensitively,
    first-seen casing kept. Invalid rows are returned rather than
    silently dropped, so the caller can flag them for manual review
    instead of discarding them.
    """
    seen_valid = set()
    seen_invalid = set()
    valid, invalid = [], []

    for raw in _read_csv_rows(csv_path):
        key = raw.lower()
        if is_valid_email(raw):
            if key in seen_valid:
                continue
            seen_valid.add(key)
            valid.append(raw)
        else:
            if key in seen_invalid:
                continue
            seen_invalid.add(key)
            invalid.append(raw)

    return valid, invalid


def unique_emails(csv_path):
    """Backwards-compatible helper: valid, de-duplicated emails only."""
    valid, _ = read_and_validate(csv_path)
    return valid


def write_emails(csv_path, emails):
    """Overwrite csv_path with one email per row."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for email in emails:
            writer.writerow([email])


def append_row(csv_path, row):
    """Append a single row to a CSV file, creating it if needed."""
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(row)


def read_column(csv_path, index=0):
    """Read a single column of values from a CSV (e.g. past sent-log emails)."""
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        return [row[index].strip() for row in csv.reader(f) if len(row) > index and row[index].strip()]


def file_size_kb(path):
    """Return file size in KB (1 decimal place), or 0 if missing."""
    if not os.path.exists(path):
        return 0.0
    return round(os.path.getsize(path) / 1024, 1)


def csv_safe(value):
    """Neutralize spreadsheet formula injection on CSV export: a field
    starting with = + - @ is treated as a formula by Excel/Sheets."""
    s = str(value) if value is not None else ""
    if s and s[0] in ("=", "+", "-", "@"):
        return "'" + s
    return s
