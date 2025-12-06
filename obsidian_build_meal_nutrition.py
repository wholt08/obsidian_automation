from __future__ import annotations
import csv
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any

import requests

# ========= CONFIG =========

VAULT_ROOT   = Path(r"C:\Users\willb\Documents\Obsidian")
ASSETS_DIR   = VAULT_ROOT / "Assets"

MEALS_RAW_CSV_PATH = ASSETS_DIR / "journal_meals_raw.csv"
MEALS_OUT_CSV_PATH = ASSETS_DIR / "journal_meals.csv"
CACHE_PATH         = ASSETS_DIR / "meal_nutrition_cache.json"

# DeepSeek API config
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# =========================


def load_cache(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache: Dict[str, Any], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def make_cache_key(date_str: str, meal_type: str, meal_text: str) -> str:
    return f"{date_str}::{meal_type}::{meal_text.strip()}"


def call_deepseek_nutrition(meal_text: str) -> Dict[str, float]:
    """
    Call DeepSeek to estimate nutrition for a single meal description.
    Returns a dict with keys: calories, protein_g, fat_g, carbs_g, fiber_g
    """

    if not DEEPSEEK_API_KEY:
        raise RuntimeError(
            "DEEPSEEK_API_KEY environment variable is not set. "
            "Set it before running this script."
        )

    prompt = f"""
You are a meticulous nutritionist estimating the nutritional values for a meal.

Meal description:
\"\"\"{meal_text}\"\"\".

Important guidelines:
- Assume realistic portion sizes for a typical adult unless the description clearly says "small" or "light".
- If oils, butter, dressings, sauces, cheese, or sugar are likely involved but not explicitly mentioned, assume they ARE present in typical amounts.
- If you are uncertain between a lower and higher calorie estimate, choose the slightly HIGHER, more conservative value.
- Do NOT try to be "optimistic" or diet-friendly; err on the side of capturing hidden calories.

Return a STRICT JSON object only, with these keys and numeric values:

{{
  "calories": <number>,
  "protein_g": <number>,
  "fat_g": <number>,
  "carbs_g": <number>,
  "fiber_g": <number>
}}

Do not include any explanation, just the JSON object.
"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "You are a precise nutrition estimation assistant."},
            {"role": "user", "content": prompt.strip()},
        ],
        "temperature": 0.2,
    }

    resp = requests.post(DEEPSEEK_BASE_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    # Adjust this if DeepSeek changes its response format
    content = data["choices"][0]["message"]["content"]

    # Try to parse JSON from the content (it should be pure JSON per the prompt)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Sometimes models wrap JSON in code fences; try to strip them out
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            # after stripping backticks, there might still be "json\n{...}"
            if "\n" in stripped:
                stripped = stripped.split("\n", 1)[1]
        parsed = json.loads(stripped)

    # Normalize and ensure all keys exist
    result = {
        "calories": float(parsed.get("calories", 0) or 0),
        "protein_g": float(parsed.get("protein_g", 0) or 0),
        "fat_g": float(parsed.get("fat_g", 0) or 0),
        "carbs_g": float(parsed.get("carbs_g", 0) or 0),
        "fiber_g": float(parsed.get("fiber_g", 0) or 0),
    }
    return result


def estimate_nutrition_with_cache(
    date_str: str,
    meal_type: str,
    meal_text: str,
    cache: Dict[str, Any],
) -> Dict[str, float]:
    key = make_cache_key(date_str, meal_type, meal_text)
    if key in cache:
        return cache[key]

    print(f"Calling DeepSeek for {date_str} {meal_type}: {meal_text[:60]}...")
    result = call_deepseek_nutrition(meal_text)
    cache[key] = result
    return result


def read_meals_raw(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"Input file not found: {path}")

    rows: list[dict] = []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Expect at least: date, meal_type, meal_text
            if not row.get("date") or not row.get("meal_type"):
                continue
            if not row.get("meal_text") or not row["meal_text"].strip():
                continue
            rows.append(
                {
                    "date": row["date"],
                    "meal_type": row["meal_type"],
                    "meal_text": row["meal_text"].strip(),
                }
            )
    return rows


def write_meals_with_nutrition(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "date",
        "meal_type",
        "meal_text",
        "calories",
        "protein_g",
        "fat_g",
        "carbs_g",
        "fiber_g",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    print(f"Vault root:       {VAULT_ROOT}")
    print(f"Assets directory: {ASSETS_DIR}")
    print(f"Input meals:      {MEALS_RAW_CSV_PATH}")
    print(f"Output meals:     {MEALS_OUT_CSV_PATH}")
    print(f"Cache file:       {CACHE_PATH}")

    if not DEEPSEEK_API_KEY:
        sys.exit(
            "DEEPSEEK_API_KEY is not set in the environment. "
            "Set it before running this script."
        )

    raw_rows = read_meals_raw(MEALS_RAW_CSV_PATH)
    print(f"Loaded {len(raw_rows)} meal rows from journal_meals_raw.csv")

    cache = load_cache(CACHE_PATH)
    print(f"Loaded cache with {len(cache)} entries")

    enriched_rows: list[dict] = []

    for r in raw_rows:
        date_str = r["date"]
        meal_type = r["meal_type"]
        meal_text = r["meal_text"]

        try:
            nutrition = estimate_nutrition_with_cache(
                date_str, meal_type, meal_text, cache
            )
        except Exception as e:
            print(f"ERROR for {date_str} {meal_type}: {e}")
            # If the API call fails, still keep the row with zeros
            nutrition = {
                "calories": 0.0,
                "protein_g": 0.0,
                "fat_g": 0.0,
                "carbs_g": 0.0,
                "fiber_g": 0.0,
            }

        enriched_rows.append(
            {
                "date": date_str,
                "meal_type": meal_type,
                "meal_text": meal_text,
                "calories": nutrition["calories"],
                "protein_g": nutrition["protein_g"],
                "fat_g": nutrition["fat_g"],
                "carbs_g": nutrition["carbs_g"],
                "fiber_g": nutrition["fiber_g"],
            }
        )

    # Save cache and output
    save_cache(cache, CACHE_PATH)
    print(f"Saved cache with {len(cache)} entries")

    enriched_rows.sort(key=lambda r: (r["date"], r["meal_type"]))
    write_meals_with_nutrition(enriched_rows, MEALS_OUT_CSV_PATH)
    print(f"Wrote {len(enriched_rows)} enriched meals to: {MEALS_OUT_CSV_PATH}")

    print("Done. Your meals are now fully snitching on you to Future Billy.")


if __name__ == "__main__":
    main()
