from __future__ import annotations
import csv
import os
import json
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import defaultdict, OrderedDict
import statistics

# Try to import matplotlib for charts
try:
    import matplotlib.pyplot as plt
    plt.style.use("dark_background")
except ImportError:
    plt = None

# Try to import requests for AI coach
try:
    import requests
except ImportError:
    requests = None

# ===================== USER CONFIG =====================
# 🔧 Change THESE, not the logic below

VAULT_ROOT = Path(r"C:\Users\willb\Documents\Obsidian")
ASSETS_DIR = VAULT_ROOT / "Assets"
SUMMARY_MD_PATH = VAULT_ROOT / "Life Summary.md"

DAILY_CSV = ASSETS_DIR / "journal_daily.csv"
MEALS_CSV = ASSETS_DIR / "journal_meals.csv"

GOALS = {
    "calories": {
        "target": 2000,
        "window_days": 30,
    },
    "protein_g": {
        "target": 140,
        "window_days": 30,
    },
    "fiber_g": {
        "target": 30,
        "window_days": 30,
    },
    "sleep_score": {
        "target_min": 7.0,
        "window_days": 14,
    },
    "workouts_per_week": {
        "target": 3,
        "window_days": 14,  # evaluate over the last 2 weeks
    },
    "weight_goal_lb": {
        "target": 200,
    },
    "investment_goal": {
        "target": 1_500_000,
    },
    "alcohol": {
        "max_drinks_per_week": 8,      # rough ceiling based on your current pattern
        "min_dry_days_per_week": 3,    # aim for at least 3 no-drink days per week
        "window_days": 30,
    },
}

# Toggle AI coach section on/off
USE_DEEPSEEK_COACH = True
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# =====================================================


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def load_daily_data():
    rows = []
    with DAILY_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["date"] = parse_date(r["date"])
            for field in ("drinks", "sleep", "water", "weight", "investments"):
                r[field] = float(r[field]) if r[field] not in ("", None) else None
            rows.append(r)
    rows.sort(key=lambda x: x["date"])
    return rows


def load_meal_data():
    daily = defaultdict(lambda: {"calories": 0.0, "protein_g": 0.0, "fiber_g": 0.0})
    if not MEALS_CSV.exists():
        return daily

    with MEALS_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = parse_date(r["date"])
            daily[d]["calories"] += float(r["calories"])
            daily[d]["protein_g"] += float(r["protein_g"])
            daily[d]["fiber_g"] += float(r["fiber_g"])

    return daily


def rolling_window(data, days: int):
    """
    Return values for entries within the last `days` days,
    EXCLUDING today so partial days don't skew averages.
    """
    today = date.today()
    cutoff = today - timedelta(days=days)
    return [v for d, v in data if cutoff <= d < today]


def avg(values):
    return round(statistics.mean(values), 1) if values else None


def summarize_sleep(daily_rows):
    sleep_vals = [(r["date"], r["sleep"]) for r in daily_rows if r["sleep"] is not None]
    window = rolling_window(sleep_vals, GOALS["sleep_score"]["window_days"])
    return avg(window)


def summarize_workouts(daily_rows):
    today = date.today()
    window_days = GOALS["workouts_per_week"]["window_days"]
    cutoff = today - timedelta(days=window_days)
    workouts = sum(
        1
        for r in daily_rows
        if cutoff <= r["date"] < today and (r.get("workout") or "").strip()
    )
    weeks = window_days / 7
    return round(workouts / weeks, 1) if weeks > 0 else 0.0


def summarize_alcohol(daily_rows):
    today = date.today()
    config = GOALS["alcohol"]
    window_days = config["window_days"]
    cutoff = today - timedelta(days=window_days)

    window_dates = sorted(
        {r["date"] for r in daily_rows if cutoff <= r["date"] < today}
    )
    if not window_dates:
        return {
            "drinks_per_week": None,
            "dry_days_per_week": None,
            "total_drinks": 0.0,
            "window_days": 0,
        }

    total_drinks = 0.0
    drink_days = 0
    for r in daily_rows:
        d = r["date"]
        if d < cutoff or d >= today:
            continue
        drinks = r["drinks"] if r["drinks"] is not None else 0.0
        total_drinks += drinks
        if drinks > 0:
            drink_days += 1

    actual_window_days = len(window_dates)
    drinks_per_week = total_drinks / actual_window_days * 7 if actual_window_days > 0 else None
    dry_days = actual_window_days - drink_days
    dry_days_per_week = dry_days / actual_window_days * 7 if actual_window_days > 0 else None

    return {
        "drinks_per_week": round(drinks_per_week, 1) if drinks_per_week is not None else None,
        "dry_days_per_week": round(dry_days_per_week, 1) if dry_days_per_week is not None else None,
        "total_drinks": round(total_drinks, 1),
        "window_days": actual_window_days,
    }


def days_since_last_sex(daily_rows):
    today = date.today()
    sex_dates = [
        r["date"]
        for r in daily_rows
        if (r.get("sex") or "").strip()
    ]
    if not sex_dates:
        return None
    last = max(sex_dates)
    return (today - last).days


def _ensure_chart_dir():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def _save_simple_message_chart(path: Path, title: str, message: str):
    if plt is None:
        return
    _ensure_chart_dir()
    plt.figure()
    plt.title(title)
    plt.text(0.5, 0.5, message, ha="center", va="center", fontsize=10)
    plt.axis("off")
    plt.tight_layout()
    path.unlink(missing_ok=True)
    plt.savefig(path)
    plt.close()


def generate_charts(daily_rows):
    """
    Generate charts and return a list of relative paths (from vault root)
    to include in the markdown.
    Always creates files, even if they just say 'Not enough data yet.'
    """
    chart_paths = []
    if plt is None:
        return chart_paths

    _ensure_chart_dir()

    today = date.today()
    cutoff_30 = today - timedelta(days=30)

    # 1) Weight trend
    weight_file = ASSETS_DIR / "weight_trend.png"
    weight_rel = "Assets/weight_trend.png"
    weight_points = [(r["date"], r["weight"]) for r in daily_rows if r["weight"] is not None]
    if len(weight_points) >= 2:
        dates_w, weights = zip(*weight_points)
        plt.figure()
        plt.plot(dates_w, weights)
        plt.xlabel("Date")
        plt.ylabel("Weight (lbs)")
        plt.title("Weight Trend")
        plt.xticks(rotation=45)
        plt.tight_layout()
        weight_file.unlink(missing_ok=True)
        plt.savefig(weight_file)
        plt.close()
    else:
        _save_simple_message_chart(weight_file, "Weight Trend", "Not enough data yet.")
    chart_paths.append(weight_rel)

    # 2) Calories last 30 days
    calories_file = ASSETS_DIR / "calories_30d.png"
    calories_rel = "Assets/calories_30d.png"
    cal_points = [
        (r["date"], r.get("calories", 0.0))
        for r in daily_rows
        if cutoff_30 <= r["date"] < today
    ]
    cal_points = [(d, v) for d, v in cal_points if v and v > 0]
    if len(cal_points) >= 2:
        dates_c, calories = zip(*cal_points)
        plt.figure()
        plt.plot(dates_c, calories)
        plt.axhline(y=GOALS["calories"]["target"])
        plt.xlabel("Date")
        plt.ylabel("Calories")
        plt.title("Calories (Last 30 Days)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        calories_file.unlink(missing_ok=True)
        plt.savefig(calories_file)
        plt.close()
    else:
        _save_simple_message_chart(calories_file, "Calories (Last 30 Days)", "Not enough data yet.")
    chart_paths.append(calories_rel)

    # 3) Drinks last 30 days
    drinks_file = ASSETS_DIR / "drinks_30d.png"
    drinks_rel = "Assets/drinks_30d.png"
    drink_points = [
        (r["date"], r["drinks"] if r["drinks"] is not None else 0.0)
        for r in daily_rows
        if cutoff_30 <= r["date"] < today
    ]
    if len(drink_points) >= 2:
        dates_d, drinks = zip(*drink_points)
        plt.figure()
        plt.plot(dates_d, drinks)
        plt.xlabel("Date")
        plt.ylabel("Drinks")
        plt.title("Alcohol (Last 30 Days)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        drinks_file.unlink(missing_ok=True)
        plt.savefig(drinks_file)
        plt.close()
    else:
        _save_simple_message_chart(drinks_file, "Alcohol (Last 30 Days)", "Not enough data yet.")
    chart_paths.append(drinks_rel)

    # 4) Workouts per week (last ~12 weeks)
    workouts_file = ASSETS_DIR / "workouts_per_week.png"
    workouts_rel = "Assets/workouts_per_week.png"
    week_counts = OrderedDict()
    for r in daily_rows:
        d = r["date"]
        if d > today:
            continue
        iso_year, iso_week, _ = d.isocalendar()
        key = (iso_year, iso_week)
        if key not in week_counts:
            week_counts[key] = 0
        if (r.get("workout") or "").strip():
            week_counts[key] += 1
    items = list(week_counts.items())[-12:]
    if items:
        labels = [f"{y}-W{w}" for (y, w), _ in items]
        values = [cnt for _, cnt in items]
        plt.figure()
        plt.plot(labels, values)
        plt.axhline(y=GOALS["workouts_per_week"]["target"])
        plt.xlabel("Week")
        plt.ylabel("Workouts")
        plt.title("Workouts per Week (Last 12 Weeks)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        workouts_file.unlink(missing_ok=True)
        plt.savefig(workouts_file)
        plt.close()
    else:
        _save_simple_message_chart(workouts_file, "Workouts per Week", "No workout data yet.")
    chart_paths.append(workouts_rel)

    # 5) Protein last 30 days
    protein_file = ASSETS_DIR / "protein_30d.png"
    protein_rel = "Assets/protein_30d.png"
    protein_points = [
        (r["date"], r.get("protein_g", 0.0))
        for r in daily_rows
        if cutoff_30 <= r["date"] < today
    ]
    protein_points = [(d, v) for d, v in protein_points if v and v > 0]
    if len(protein_points) >= 2:
        dates_p, proteins = zip(*protein_points)
        plt.figure()
        plt.plot(dates_p, proteins)
        plt.axhline(y=GOALS["protein_g"]["target"])
        plt.xlabel("Date")
        plt.ylabel("Protein (g)")
        plt.title("Protein (Last 30 Days)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        protein_file.unlink(missing_ok=True)
        plt.savefig(protein_file)
        plt.close()
    else:
        _save_simple_message_chart(protein_file, "Protein (Last 30 Days)", "Not enough data yet.")
    chart_paths.append(protein_rel)

    # 6) Fiber last 30 days
    fiber_file = ASSETS_DIR / "fiber_30d.png"
    fiber_rel = "Assets/fiber_30d.png"
    fiber_points = [
        (r["date"], r.get("fiber_g", 0.0))
        for r in daily_rows
        if cutoff_30 <= r["date"] < today
    ]
    fiber_points = [(d, v) for d, v in fiber_points if v and v > 0]
    if len(fiber_points) >= 2:
        dates_f, fibers = zip(*fiber_points)
        plt.figure()
        plt.plot(dates_f, fibers)
        plt.axhline(y=GOALS["fiber_g"]["target"])
        plt.xlabel("Date")
        plt.ylabel("Fiber (g)")
        plt.title("Fiber (Last 30 Days)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        fiber_file.unlink(missing_ok=True)
        plt.savefig(fiber_file)
        plt.close()
    else:
        _save_simple_message_chart(fiber_file, "Fiber (Last 30 Days)", "Not enough data yet.")
    chart_paths.append(fiber_rel)

    return chart_paths


def compute_overall_tier(
    calories_avg,
    protein_avg,
    fiber_avg,
    sleep_avg,
    workouts_rate,
    alcohol_stats,
    current_weight,
):
    """
    Return dict with label, emoji, description, gif path.
    Score is based on how many goals you're hitting.
    """
    score = 0

    # Calories: within 10% above target
    if calories_avg is not None:
        if calories_avg <= GOALS["calories"]["target"] * 1.1:
            score += 1

    # Protein: at least 90% of target
    if protein_avg is not None:
        if protein_avg >= GOALS["protein_g"]["target"] * 0.9:
            score += 1

    # Fiber: at least 80% of target
    if fiber_avg is not None:
        if fiber_avg >= GOALS["fiber_g"]["target"] * 0.8:
            score += 1

    # Sleep: hitting target
    if sleep_avg is not None:
        if sleep_avg >= GOALS["sleep_score"]["target_min"]:
            score += 1

    # Workouts: at or above target
    if workouts_rate is not None:
        if workouts_rate >= GOALS["workouts_per_week"]["target"]:
            score += 1

    # Alcohol: within preferred band
    drinks_pw = alcohol_stats.get("drinks_per_week")
    dry_pw = alcohol_stats.get("dry_days_per_week")
    if drinks_pw is not None and dry_pw is not None:
        alc_goal = GOALS["alcohol"]
        if drinks_pw <= alc_goal["max_drinks_per_week"] and dry_pw >= alc_goal["min_dry_days_per_week"]:
            score += 1

    # Weight: within 5 lbs of goal counts as a win
    if current_weight is not None:
        if current_weight <= GOALS["weight_goal_lb"]["target"] + 5:
            score += 1

    # Map score to tier
    if score <= 2:
        return {
            "label": "Charmander",
            "emoji": "🔸",
            "description": "You’re in starter mode. Things are a bit wobbly, but you’ve got all the potential.",
            "gif_rel": "Assets/charmander.gif",
        }
    elif score <= 4:
        return {
            "label": "Charmeleon",
            "emoji": "🔺",
            "description": "You’re doing pretty well overall. A few tweaks would level you up fast.",
            "gif_rel": "Assets/charmeleon.gif",
        }
    else:
        return {
            "label": "Charzard",
            "emoji": "🔥",
            "description": "You’re in Charzard form. Strong trends, good habits, just keep the fire pointed in the right direction.",
            "gif_rel": "Assets/charzard.gif",
        }


def compute_streak(flag_days: set[date]) -> int:
    """
    Current streak in days, counting backwards from today.
    Any day not in flag_days breaks the streak.
    """
    today = date.today()
    streak = 0
    d = today
    while True:
        if d in flag_days:
            streak += 1
            d = d - timedelta(days=1)
        else:
            break
    return streak


def compute_streaks(daily_rows):
    # Alcohol-free days (no drinks or 0)
    alcohol_free_days = {
        r["date"]
        for r in daily_rows
        if (r["drinks"] is None or r["drinks"] == 0)
    }

    # Workout days
    workout_days = {
        r["date"]
        for r in daily_rows
        if (r.get("workout") or "").strip()
    }

    # Protein target days
    protein_target = GOALS["protein_g"]["target"]
    protein_hit_days = {
        r["date"]
        for r in daily_rows
        if r.get("protein_g", 0.0) >= protein_target
    }

    alcohol_streak = compute_streak(alcohol_free_days)
    workout_streak = compute_streak(workout_days)
    protein_streak = compute_streak(protein_hit_days)

    badges = []
    if alcohol_streak >= 7:
        badges.append("🏅 7+ day alcohol-free streak.")
    if workout_streak >= 7:
        badges.append("🏅 7+ day workout streak.")
    if protein_streak >= 7:
        badges.append("🏅 7+ day protein target streak.")

    return {
        "alcohol_streak": alcohol_streak,
        "workout_streak": workout_streak,
        "protein_streak": protein_streak,
        "badges": badges,
    }


def generate_ai_coach(metrics: dict) -> str | None:
    """
    Optional AI coach summary using DeepSeek.
    Safe: returns None if anything fails or is disabled.
    """
    if not USE_DEEPSEEK_COACH:
        print("[AI Coach] Disabled via USE_DEEPSEEK_COACH = False")
        return None

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("[AI Coach] DEEPSEEK_API_KEY not set; skipping AI coach.")
        return None
    if requests is None:
        print("[AI Coach] 'requests' library not available; skipping AI coach.")
        return None

    prompt = (
        "You are a supportive but direct health and habits coach. "
        "The user is trying to lose weight, improve fiber, keep protein decent, "
        "sleep better, move their body regularly, and keep alcohol reasonable. "
        "Below are their recent metrics and goals.\n\n"
        f"{json.dumps(metrics, indent=2)}\n\n"
        "Write 3–5 sentences that summarize how they are doing overall, "
        "and give 1–2 specific, actionable suggestions for the coming week. "
        "Focus on trends, not perfection. Do not restate every number. "
        "Do not use emoji."
    )

    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a concise, supportive coach."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.5,
                "max_tokens": 300,
            },
            timeout=20,
        )
        if response.status_code != 200:
            print(f"[AI Coach] DeepSeek returned status {response.status_code}")
            return None
        data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {}).get("content")
        if not message:
            print("[AI Coach] No content in DeepSeek response.")
            return None
        print("[AI Coach] Successfully generated AI coach text.")
        return message.strip()
    except Exception as e:
        print(f"[AI Coach] Error calling DeepSeek: {e}")
        return None


def build_summary():
    daily_rows = load_daily_data()
    meals = load_meal_data()

    # Merge meal nutrition into daily rows
    for r in daily_rows:
        m = meals.get(r["date"], {})
        r["calories"] = m.get("calories", 0.0)
        r["protein_g"] = m.get("protein_g", 0.0)
        r["fiber_g"] = m.get("fiber_g", 0.0)

    # --- CALCULATIONS ---

    def roll(field, days):
        series = [
            (r["date"], r[field])
            for r in daily_rows
            if r.get(field) is not None and r[field] > 0
        ]
        return avg(rolling_window(series, days))

    calories_avg = roll("calories", GOALS["calories"]["window_days"])
    protein_avg = roll("protein_g", GOALS["protein_g"]["window_days"])
    fiber_avg = roll("fiber_g", GOALS["fiber_g"]["window_days"])
    sleep_avg = summarize_sleep(daily_rows)
    workouts_rate = summarize_workouts(daily_rows)
    alcohol_stats = summarize_alcohol(daily_rows)
    sex_gap_days = days_since_last_sex(daily_rows)

    weights = [(r["date"], r["weight"]) for r in daily_rows if r["weight"] is not None]
    current_weight = weights[-1][1] if weights else None

    investments = [r["investments"] for r in daily_rows if r["investments"] is not None]
    current_investments = investments[-1] if investments else None

    # Overall tier
    tier = compute_overall_tier(
        calories_avg,
        protein_avg,
        fiber_avg,
        sleep_avg,
        workouts_rate,
        alcohol_stats,
        current_weight,
    )

    # Streaks / badges
    streaks = compute_streaks(daily_rows)

    # AI coach metrics package
    metrics_for_ai = {
        "calories_30d_avg": calories_avg,
        "calories_target": GOALS["calories"]["target"],
        "protein_30d_avg": protein_avg,
        "protein_target": GOALS["protein_g"]["target"],
        "fiber_30d_avg": fiber_avg,
        "fiber_target": GOALS["fiber_g"]["target"],
        "sleep_14d_avg": sleep_avg,
        "sleep_target_min": GOALS["sleep_score"]["target_min"],
        "workouts_per_week": workouts_rate,
        "workouts_target": GOALS["workouts_per_week"]["target"],
        "alcohol_drinks_per_week": alcohol_stats.get("drinks_per_week"),
        "alcohol_dry_days_per_week": alcohol_stats.get("dry_days_per_week"),
        "weight_current": current_weight,
        "weight_goal": GOALS["weight_goal_lb"]["target"],
        "sex_gap_days": sex_gap_days,
    }
    ai_coach_text = generate_ai_coach(metrics_for_ai)

    # --- CHARTS ---
    chart_paths = generate_charts(daily_rows)

    # --- MARKDOWN OUTPUT ---

    today = date.today()

    lines = [
        f"_Updated: {today.isoformat()}_",
        "",
        f"**Overall Status:** {tier['emoji']} {tier['label']} – {tier['description']}",
        "",
        f"![]({tier['gif_rel']})",
        "",
    ]

    # AI Coach right after overall status + gif
    if ai_coach_text:
        quoted = "\n".join("> " + line for line in ai_coach_text.splitlines())
        lines += [
            "## AI Coach",
            quoted,
            "",
        ]

    # Snapshot
    lines += [
        "## Snapshot",
        f"- **Calories (30d avg):** {calories_avg or 'n/a'} / {GOALS['calories']['target']}",
        f"- **Protein (30d avg):** {protein_avg or 'n/a'} g / {GOALS['protein_g']['target']}",
        f"- **Fiber (30d avg):** {fiber_avg or 'n/a'} g / {GOALS['fiber_g']['target']}",
        f"- **Sleep (14d avg):** {sleep_avg or 'n/a'} / 10",
        f"- **Workouts/week:** {workouts_rate}",
        f"- **Weight:** {current_weight or 'n/a'} lbs (goal {GOALS['weight_goal_lb']['target']})",
    ]

    if current_investments is not None:
        lines.append(
            f"- **Investments:** ${current_investments:,.0f} / "
            f"${GOALS['investment_goal']['target']:,.0f}"
        )

    drinks_pw = alcohol_stats["drinks_per_week"]
    dry_pw = alcohol_stats["dry_days_per_week"]

    if drinks_pw is not None and dry_pw is not None:
        lines.append(
            f"- **Alcohol (30d):** ~{drinks_pw} drinks/week, ~{dry_pw} dry days/week"
        )

    if sex_gap_days is not None:
        lines.append(f"- **Days since sex:** {sex_gap_days}")
    else:
        lines.append("- **Days since sex:** n/a")

    # Streaks
    lines += [
        "",
        "## Streaks & Badges",
        f"- **Alcohol-free streak:** {streaks['alcohol_streak']} days",
        f"- **Workout streak:** {streaks['workout_streak']} days",
        f"- **Protein target streak:** {streaks['protein_streak']} days",
    ]
    if streaks["badges"]:
        for b in streaks["badges"]:
            lines.append(f"- {b}")
    else:
        lines.append("- No special badges yet. (Which is frankly an invitation.)")

    # Wins / concerns / focus
    wins = []
    concerns = []
    actions = []

    # Workouts
    if workouts_rate >= GOALS["workouts_per_week"]["target"]:
        wins.append(f"Workout consistency is solid (~{workouts_rate}/week).")
    else:
        concerns.append("Workout frequency is below your goal of 3 per week.")
        actions.append("Aim for at least 3 workouts this week, even if they’re short sessions.")

    # Sleep
    if sleep_avg is not None:
        if sleep_avg >= GOALS["sleep_score"]["target_min"]:
            wins.append(f"Sleep quality feels good recently (avg {sleep_avg}/10).")
        else:
            concerns.append("Sleep ratings have dipped below your comfort zone (7/10).")
            actions.append("Prioritize wind-down time, screens-off, and a consistent bedtime.")

    # Protein
    if protein_avg is not None:
        if protein_avg < GOALS["protein_g"]["target"]:
            concerns.append("Protein intake is on the low side relative to your target.")
            actions.append("Add a protein shake or protein-heavy meal on lighter days.")
        else:
            wins.append("Protein intake is generally on track.")

    # Fiber
    if fiber_avg is not None:
        if fiber_avg < GOALS["fiber_g"]["target"]:
            concerns.append("Fiber intake is below your doctor-recommended target.")
            actions.append("Add beans, oats, lentils, or berries to daily meals to boost fiber.")
        else:
            wins.append("Fiber intake looks healthy overall.")

    # Weight status (simple)
    if current_weight is not None:
        if current_weight > GOALS["weight_goal_lb"]["target"]:
            concerns.append(
                f"Weight is above your goal ({current_weight} lbs vs {GOALS['weight_goal_lb']['target']} lbs)."
            )
        else:
            wins.append(
                f"Weight is at or below your goal range ({current_weight} lbs)."
            )

    # Alcohol insights
    if drinks_pw is not None and dry_pw is not None:
        alc_goal = GOALS["alcohol"]
        if drinks_pw <= alc_goal["max_drinks_per_week"] and dry_pw >= alc_goal["min_dry_days_per_week"]:
            wins.append(
                f"Alcohol intake (~{drinks_pw} drinks/week, ~{dry_pw} dry days/week) "
                "is within your target range."
            )
        else:
            concerns.append(
                f"Alcohol is above your preferred range (~{drinks_pw} drinks/week, ~{dry_pw} dry days/week)."
            )
            actions.append("Add one more alcohol-free day this week or reduce drinks on one of your usual nights.")

    lines += [
        "",
        "## What’s Going Well",
    ]
    if wins:
        lines.extend(f"- {w}" for w in wins)
    else:
        lines.append("- (Nothing notable yet)")

    lines += [
        "",
        "## What Needs Attention",
    ]
    if concerns:
        lines.extend(f"- {c}" for c in concerns)
    else:
        lines.append("- Nothing urgent.")

    lines += [
        "",
        "## Focus This Week",
    ]
    if actions:
        lines.extend(f"- {a}" for a in actions[:3])
    else:
        lines.append("- Keep doing what you’re doing.")

    # Charts section
    if chart_paths:
        lines += [
            "",
            "## Charts",
        ]
        for rel in chart_paths:
            lines.append(f"![]({rel})")
        lines.append("")

    SUMMARY_MD_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    build_summary()
    print(f"Wrote life summary to {SUMMARY_MD_PATH}")
