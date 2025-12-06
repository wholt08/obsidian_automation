from __future__ import annotations
import re
import sys
import csv
from pathlib import Path
from datetime import date
from dateutil.parser import isoparse
import yaml

# =================== CONFIG ===================

VAULT_ROOT   = Path(r"C:\Users\willb\Documents\Obsidian")
JOURNAL_ROOT = VAULT_ROOT / r"Areas\Journal"
ASSETS_DIR   = VAULT_ROOT / "Assets"

ASSETS_DIR.mkdir(parents=True, exist_ok=True)

DAILY_CSV_PATH      = ASSETS_DIR / "journal_daily.csv"
MEALS_RAW_CSV_PATH  = ASSETS_DIR / "journal_meals_raw.csv"

# Only care about these frontmatter properties going forward
CANONICAL_FIELDS = [
    "date",
    "drinks",
    "sex",
    "workout",
    "breakfast",
    "lunch",
    "dinner",
    "sleep",
    "water",
    "weight",
    "Investments",
]

# ==============================================

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*", re.S)


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except Exception:
        return {}


def find_daily_notes(root: Path) -> list[Path]:
    """
    Look for daily notes in Areas/Journal/YYYY/MM/*.md
    """
    if not root.exists():
        sys.exit(f"Journal path not found: {root}")
    years = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()]
    notes: list[Path] = []
    for y in years:
        for m in y.iterdir():
            if m.is_dir():
                notes.extend(m.glob("*.md"))
    return notes


def coerce_date(v) -> date | None:
    if not v:
        return None
    try:
        return isoparse(str(v)).date()
    except Exception:
        return None


def num(v):
    """
    Pull a float out of whatever the user typed.
    '2 bottles', '82.5kg', 3 -> 2.0, 82.5, 3.0
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"[-+]?\d*\.?\d+", str(v))
    return float(m.group()) if m else None


def nonempty(v) -> bool:
    return False if v is None else (str(v).strip() != "")


def load_journal_entries(notes: list[Path]) -> list[dict]:
    """
    Load notes and extract only the canonical properties.
    Ignores legacy frontmatter fields that no longer exist.
    """
    entries: list[dict] = []

    for p in notes:
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        fm = parse_frontmatter(txt)
        if not fm:
            continue

        d = coerce_date(fm.get("date"))
        if not d:
            # Fallback: try to derive from filename like '2025-12-01 Some title'
            m = re.search(r"(\d{4}-\d{2}-\d{2})", p.stem)
            d = isoparse(m.group(1)).date() if m else None
        if not d:
            # No usable date = skip
            continue

        # Normalize numeric vs text fields
        drinks = num(fm.get("drinks"))
        sleep  = num(fm.get("sleep"))
        water  = num(fm.get("water"))
        weight = num(fm.get("weight"))
        investments = num(fm.get("Investments"))

        entry = {
            "date": d,
            "drinks": drinks,
            "sex": fm.get("sex"),
            "workout": fm.get("workout"),
            "breakfast": fm.get("breakfast"),
            "lunch": fm.get("lunch"),
            "dinner": fm.get("dinner"),
            "sleep": sleep,
            "water": water,
            "weight": weight,
            "investments": investments,
            "path": p,
        }
        entries.append(entry)

    # Sort by date just to keep things nice
    entries.sort(key=lambda e: e["date"])
    return entries


def write_daily_csv(entries: list[dict], path: Path) -> None:
    """
    One row per day, with the core fields plus meal text.
    """
    fieldnames = [
        "date",
        "drinks",
        "sex",
        "workout",
        "sleep",
        "water",
        "weight",
        "investments",
        "breakfast",
        "lunch",
        "dinner",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for e in entries:
            row = {
                "date": e["date"].isoformat(),
                "drinks": "" if e["drinks"] is None else e["drinks"],
                "sex": e["sex"] or "",
                "workout": e["workout"] or "",
                "sleep": "" if e["sleep"] is None else e["sleep"],
                "water": "" if e["water"] is None else e["water"],
                "weight": "" if e["weight"] is None else e["weight"],
                "investments": "" if e["investments"] is None else e["investments"],
                "breakfast": (e["breakfast"] or "").strip(),
                "lunch": (e["lunch"] or "").strip(),
                "dinner": (e["dinner"] or "").strip(),
            }
            writer.writerow(row)


def write_meals_raw_csv(entries: list[dict], path: Path) -> None:
    """
    One row per meal (breakfast/lunch/dinner) with raw text only.
    This is what the DeepSeek nutrition script will consume later.
    """
    fieldnames = ["date", "meal_type", "meal_text"]

    rows = []
    for e in entries:
        d_str = e["date"].isoformat()
        for meal_type in ("breakfast", "lunch", "dinner"):
            text = e.get(meal_type)
            if nonempty(text):
                rows.append(
                    {
                        "date": d_str,
                        "meal_type": meal_type,
                        "meal_text": str(text).strip(),
                    }
                )

    # Sort by date then meal_type for sanity
    rows.sort(key=lambda r: (r["date"], r["meal_type"]))

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    print(f"Vault root:   {VAULT_ROOT}")
    print(f"Journal root: {JOURNAL_ROOT}")

    notes = find_daily_notes(JOURNAL_ROOT)
    print(f"Found {len(notes)} journal files")

    entries = load_journal_entries(notes)
    print(f"Loaded {len(entries)} entries with usable dates")

    write_daily_csv(entries, DAILY_CSV_PATH)
    print(f"Wrote daily dataset to: {DAILY_CSV_PATH}")

    write_meals_raw_csv(entries, MEALS_RAW_CSV_PATH)
    print(f"Wrote raw meals dataset to: {MEALS_RAW_CSV_PATH}")

    print("Done. Your life is now slightly more machine-readable.")


if __name__ == "__main__":
    main()
