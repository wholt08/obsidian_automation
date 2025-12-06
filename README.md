Obsidian Python Automations

These are lightweight Python scripts I use to extract structured data from my Obsidian journal and export it to CSV for analysis, visualization, or long-term tracking.

They assume a consistent daily journal format with YAML frontmatter and are designed to work offline, locally, and without Obsidian plugins.

This is not a polished framework. It’s a set of practical scripts that work well if your vault is reasonably structured.

What This Does (High-Level)

Reads daily journal notes from an Obsidian vault

Extracts selected YAML properties (and in some cases body content)

Writes normalized CSV files you can analyze in Excel, Google Sheets, Python, etc.

Designed to run automatically (for example via Windows Task Scheduler)

Use cases include:

Long-term habit tracking

Health and nutrition analysis

Life stats and trend analysis

Personal “life dashboard” data feeds

Assumptions About Your Obsidian Vault

These scripts assume:

Daily notes live in a known folder (e.g. Journal/Daily)

Each daily note uses YAML frontmatter

Property names are consistent across notes

Dates are encoded either in the filename or YAML

Example daily note structure:

---
date: 2024-11-30
sleep: 7.5
weight: 212
steps: 10324
mood: calm
breakfast: greek yogurt, berries
lunch: chicken wrap
dinner: tacos
---


Free-form markdown below the frontmatter is fine.

If your structure is different, you’ll need to tweak paths or property names.

Scripts Overview
1. Journal Property → CSV Export

Extracts selected YAML properties from all daily notes and writes them to a CSV file.

Typical output:

One row per day

Columns for date + selected properties

Missing values left blank

Useful for:

Habit tracking

Health stats

Long-term trends

2. “Memory Lane” Journal Lookback

Scans historical journals and surfaces entries written on the same calendar date in prior years.

Example:

“Here’s what you wrote on Nov 30 in 2021 and 2022”

This one is more for reflection than CSV analysis, but runs on the same assumptions.

3. Life Summary / Derived Metrics (Optional)

Some scripts:

Aggregate daily data

Produce rolling averages or summaries

Feed dashboards or charts

These usually depend on the raw CSV exports from Script #1.

How to Run
1. Requirements

Python 3.10+

Obsidian vault stored locally

Install dependencies:

pip install pyyaml pandas


(If a script imports something extra, it will be obvious.)

2. Configure Paths

At the top of each script, update:

VAULT_PATH

DAILY_NOTE_PATH

OUTPUT_CSV_PATH

Example:

VAULT_PATH = r"C:\Users\You\Documents\ObsidianVault"
DAILY_NOTE_PATH = "Journal/Daily"
OUTPUT_CSV_PATH = "Exports/journal_data.csv"


Paths are relative to the vault unless otherwise noted.

3. Run Manually
python export_journal_to_csv.py


CSV output will be overwritten or appended depending on the script.

4. Run Automatically (Optional)

These scripts work well with:

Windows Task Scheduler

cron (macOS/Linux)

I run mine once daily in the morning to keep CSVs up to date automatically.

Notes, Caveats, and Philosophy

These scripts trust your data. No validation, no guardrails.

YAML inconsistencies will break things.

Commas in YAML values are generally fine. They’ll be properly quoted in CSV.

This is intentionally script-based instead of plugin-based. Less magic, easier to customize, easier to debug.

You will probably want to:

Rename properties

Remove fields you don’t care about

Add your own derived metrics

That’s kind of the point.

Not a Supported Project

This is shared for learning and inspiration.
Feel free to adapt, fork, or cannibalize.

I can’t promise ongoing support, but the code should be readable enough to modify safely.

License

Do whatever you want. Attribution appreciated, not required.
