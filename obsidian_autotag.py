import os
import sys
import re
import argparse
from datetime import datetime, timedelta

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml. Install with: pip install pyyaml")
    sys.exit(1)

# === CONFIGURATION ===

# Tag rules: tag_name -> list of regex patterns
TAG_RULES = {
    "camille": [
        r"\bcamille\b",
    ],
    "scout": [
        r"\bscout\b",
    ],
    "kyle": [
        r"\bkyle\b",
    ],
    "matt": [
        r"\bmatt\b",
    ],
    "teddy": [
        r"\bteddy\b",
    ],
    "emily": [
        r"\bemily\b",
    ],
    "fire": [
        r"\bFIRE\b",
        r"\bfinancial independence\b",
        r"\bretire early\b",
        r"\bretirement\b",
        r"\bVTSAX\b",
        r"\bVTIAX\b",
        r"\bindex fund(s)?\b",
        r"\binvest(ing|ment|ments)?\b",
        r"\bbrokerage\b",
        r"\bnest egg\b",
        r"\b(net ?worth|NW)\b",
        r"\bbudget(ing)?\b",
        r"\bexpenses?\b",
        r"\bsavings rate\b",
        r"\bside hustle\b",
        r"\bbusiness\b",
    ],
    "health": [
        r"\bhealth(y)?\b",
        r"\bworkout(s)?\b",
        r"\bgym\b",
        r"\brun(ning|s)?\b",
        r"\bcycling\b",
        r"\bbox(ing)?\b",
        r"\bF45\b",
        r"\bHRV\b",
    ],
    "diet": [
        r"\bcalorie(s)?\b",
        r"\bprotein\b",
        r"\bmacro(s)?\b",
        r"\bbinge\b",
        r"\bovereat(ing)?\b",
        r"\bcut(ting)?\b",
        r"\bdeficit\b",
        r"\bdiet\b",
        r"\bmeal log\b",
    ],
    "trips": [
        r"\btrip(s)?\b",
        r"\btravel(ing)?\b",
        r"\broad trip\b",
        r"\bitinerary\b",
        r"\bAirbnb\b",
        r"\bhotel\b",
        r"\bcamping\b",
        r"\bbackpacking\b",
    ],
    "travel": [
        r"\bflight(s)?\b",
        r"\bfly(ing)?\b",
        r"\bairport\b",
        r"\bTSA\b",
        r"\bboarding pass\b",
        r"\bpacking list\b",
        r"\bcarry[- ]on\b",
        r"\bchecked bag\b",
    ],
    "goals": [
        r"\bgoal(s)?\b",
        r"\bOKR(s)?\b",
        r"\bmilestone(s)?\b",
        r"\bquarter(ly)? goal(s)?\b",
        r"\btarget(s)?\b",
    ],
    "dreams": [
        r"\bdream(s|ed|ing)?\b",
        r"\bdream journal\b",
        r"\blucid dream(s|ing)?\b",
    ],
    "book": [
        r"\bbook(s)?\b",
        r"\bnovel(s)?\b",
        r"\bchapter\b",
        r"\bTBR\b",
        r"\bread(ing)? list\b",
    ],
    "ai": [
        r"\bAI\b",
        r"\bLLM(s)?\b",
        r"\bGPT\b",
        r"\blanguage model(s)?\b",
        r"\bembedding(s)?\b",
        r"\bvector DB\b",
    ],
    "tech": [
        r"\btech(nology)?\b",
        r"\bSnowflake\b",
        r"\bDatabricks\b",
        r"\bKafka\b",
        r"\bPython\b",
        r"\bSQL\b",
        r"\bDocker\b",
        r"\bKubernetes\b",
        r"\blaptop\b",
        r"\bdesktop\b",
    ],
    "planning": [
        r"\bplan(s|ning)?\b",
        r"\broadmap(s)?\b",
        r"\bagenda\b",
        r"\bto[- ]do\b",
        r"\bchecklist\b",
    ],
}

# Precompile patterns for speed
COMPILED_TAG_RULES = {
    tag: [re.compile(pat, re.IGNORECASE) for pat in patterns]
    for tag, patterns in TAG_RULES.items()
}


# === FRONT MATTER HELPERS ===

def split_front_matter(text):
    """
    Split markdown text into (front_matter_dict, content_str).
    If no front matter, returns ({}, original_text).
    """
    lines = text.splitlines()
    if len(lines) >= 3 and lines[0].strip() == "---":
        # Find closing ---
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm_text = "\n".join(lines[1:i])
                content = "\n".join(lines[i+1:]) + ("\n" if text.endswith("\n") else "")
                try:
                    fm_data = yaml.safe_load(fm_text) or {}
                except yaml.YAMLError:
                    fm_data = {}
                if not isinstance(fm_data, dict):
                    fm_data = {}
                return fm_data, content
    # No front matter
    return {}, text


def join_front_matter(fm_data, content):
    """
    Join front matter dict and content back into markdown text.
    Ensures valid YAML front matter at the top.
    """
    if not fm_data:
        return content

    fm_text = yaml.safe_dump(fm_data, sort_keys=False).strip()
    return f"---\n{fm_text}\n---\n\n{content.lstrip()}"



def ensure_tags_list(fm_data):
    """
    Ensure fm_data has a 'tags' field that is a list of strings.
    Mutates fm_data and returns the list.
    """
    tags = fm_data.get("tags")
    if tags is None:
        fm_data["tags"] = []
        return fm_data["tags"]

    if isinstance(tags, str):
        # split by comma or space
        parts = re.split(r"[,\s]+", tags.strip())
        fm_data["tags"] = [t for t in parts if t]
        return fm_data["tags"]

    if isinstance(tags, list):
        # normalize to strings
        fm_data["tags"] = [str(t) for t in tags if t]
        return fm_data["tags"]

    # Anything else: replace with empty list
    fm_data["tags"] = []
    return fm_data["tags"]


# === TAGGING LOGIC ===

def infer_tags_from_text(text):
    """
    Return a set of tag names that should be applied based on TAG_RULES.
    """
    found = set()
    for tag, patterns in COMPILED_TAG_RULES.items():
        for pat in patterns:
            if pat.search(text):
                found.add(tag)
                break  # no need to test other patterns for this tag
    return found


def process_file(path, cutoff_dt, dry_run=False):
    """
    Process a single markdown file if modified after cutoff_dt.
    Returns (changed: bool, added_tags: set).
    """
    mtime = datetime.fromtimestamp(os.path.getmtime(path))
    if mtime < cutoff_dt:
        return False, set()

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    fm_data, content = split_front_matter(text)
    tags_list = ensure_tags_list(fm_data)
    existing = set(tags_list)

    inferred = infer_tags_from_text(text)
    new_tags = inferred - existing

    if not new_tags:
        return False, set()

    # Update tags, sort for consistency
    tags_list.extend(sorted(new_tags))
    # Remove duplicates while preserving order
    seen = set()
    deduped = []
    for t in tags_list:
        if t not in seen:
            seen.add(t)
            deduped.append(t)
    fm_data["tags"] = deduped

    new_text = join_front_matter(fm_data, content)

    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)

    return True, new_tags


def walk_vault(vault_path, hours, dry_run=False):
    cutoff_dt = datetime.now() - timedelta(hours=hours)
    changed_files = 0
    total_new_tags = 0

    for root, dirs, files in os.walk(vault_path):
        for name in files:
            if not name.lower().endswith(".md"):
                continue
            path = os.path.join(root, name)
            changed, new_tags = process_file(path, cutoff_dt, dry_run=dry_run)
            if changed:
                changed_files += 1
                total_new_tags += len(new_tags)
                print(f"[UPDATED] {path}  +{', '.join(sorted(new_tags))}")

    print(f"\nDone. Files updated: {changed_files}, tags added: {total_new_tags}")


def main():
    parser = argparse.ArgumentParser(description="Auto-tag Obsidian notes based on regex rules.")
    parser.add_argument("vault", help="Path to Obsidian vault directory")
    parser.add_argument("--hours", type=int, default=24,
                        help="How many past hours of modified files to process (default: 24)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write changes, just print what would happen")
    args = parser.parse_args()

    vault_path = os.path.abspath(args.vault)
    if not os.path.isdir(vault_path):
        print(f"Vault path does not exist or is not a directory: {vault_path}")
        sys.exit(1)

    walk_vault(vault_path, args.hours, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
