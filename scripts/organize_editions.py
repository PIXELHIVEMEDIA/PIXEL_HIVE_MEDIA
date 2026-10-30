
import json
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path("pixelhive-research")
QUEUE_FILE = ROOT / "review-queue.json"
OUTPUT_DIR = ROOT / "editions"

TZ = ZoneInfo("Africa/Nairobi")
now = datetime.now(timezone.utc).astimezone(TZ)

if not QUEUE_FILE.exists():
    raise SystemExit(
        "ERROR: review-queue.json not found. "
        "Run scripts/collect_news.py first."
    )

with QUEUE_FILE.open("r", encoding="utf-8") as file:
    queue = json.load(file)

schedule = __import__("os").environ.get("SCHEDULE", "")

if schedule == "7 2 * * *":
    edition = "Morning Signal"
    edition_key = "morning"
    description = "Overnight developments and stories to watch today."
elif schedule == "7 10 * * *":
    edition = "The Midday Pulse"
    edition_key = "midday"
    description = "Important developments and updates available by midday."
elif schedule == "7 16 * * *":
    edition = "The Evening Wrap"
    edition_key = "evening"
    description = "A roundup of the day's significant stories."
else:
    edition_key = "morning" if now.hour < 10 else (
        "midday" if now.hour < 16 else "evening"
    )
    edition = {
        "morning": "Morning Signal",
        "midday": "The Midday Pulse",
        "evening": "The Evening Wrap",
    }[edition_key]
    description = "Edition organizer test run; confirm the edition before use."

CATEGORY_TERMS = {
    "Africa": [
        "kenya", "africa", "nairobi", "uganda", "tanzania", "rwanda",
        "ethiopia", "nigeria", "ghana", "south africa", "somalia",
        "sudan", "congo", "african union"
    ],
    "Politics": [
        "president", "parliament", "minister", "government", "election",
        "vote", "political", "senate", "governor", "opposition",
        "policy", "lawmakers", "party leader"
    ],
    "Business": [
        "business", "economy", "market", "company", "companies",
        "bank", "banks", "stock", "shares", "trade", "jobs",
        "investment", "investor", "inflation", "prices", "startup",
        "finance", "revenue", "currency"
    ],
    "Technology": [
        "technology", "tech", "artificial intelligence", " AI ",
        "cyber", "software", "smartphone", "internet", "digital",
        "robot", "chip", "app", "data breach", "social media"
    ],
    "Sports": [
        "football", "soccer", "rugby", "cricket", "tennis",
        "athletics", "olympic", "champions league", "premier league",
        "match", "tournament", "player", "coach", "team", "sport"
    ],
}

SENSITIVE_TERMS = [
    "killed", "dead", "death toll", "casualties", "rape",
    "sexual assault", "suicide", "self-harm", "terror attack",
    "hostage", "coup", "election result", "fraud allegation",
    "accused", "alleged", "court ruling", "outbreak", "epidemic",
    "pandemic", "war crime", "genocide", "explosion",
    "mass shooting", "abuse", "sanctions", "military strike",
    "breaking", "fatal", "died", "murder", "bombing", "kidnap"
]

def category_for(title):
    text = f" {title.lower()} "
    scores = Counter()
    for category, terms in CATEGORY_TERMS.items():
        for term in terms:
            if term.lower() in text:
                scores[category] += 1
    if scores:
        return scores.most_common(1)[0][0]
    return "World"

def parse_date(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None

def sensitive(title):
    text = title.lower()
    return any(term in text for term in SENSITIVE_TERMS)

def age_hours(story):
    published = parse_date(story.get("published_at"))
    if not published:
        return None
    return (now.astimezone(timezone.utc) - published).total_seconds() / 3600

# Deduplicate by URL, retaining the first occurrence.
unique = {}
for story in queue.get("stories", []):
    url = (story.get("url") or "").strip()
    title = (story.get("title") or "").strip()
    if not url or not title:
        continue
    if url not in unique:
        unique[url] = dict(story)

stories = list(unique.values())

# Categorize every lead and separate review-only items.
ready_for_editor = []
held_for_review = []
excluded_old = []

for story in stories:
    story["category"] = category_for(story["title"])
    story["edition"] = edition
    story["status"] = "UNVERIFIED_HEADLINE_LEAD"
    story["publication_allowed"] = False

    age = age_hours(story)
    reasons = list(story.get("review_flags") or [])

    if sensitive(story["title"]):
        reasons.append("Sensitive subject: human review required")

    if age is None:
        reasons.append("Missing or unreadable publication date")
    elif age < -24:
        reasons.append("Publication date is unexpectedly in the future")
    elif age > 72:
        excluded_old.append({
            **story,
            "review_flags": reasons + ["Older than 72 hours; assess relevance"]
        })
        continue

    story["review_flags"] = sorted(set(reasons))

    if story["review_flags"]:
        held_for_review.append(story)
    else:
        story["status"] = "UNVERIFIED_NEEDS_EDITORIAL_CHECKS"
        ready_for_editor.append(story)

# Newer stories first; missing dates are sorted last.
ready_for_editor.sort(
    key=lambda s: parse_date(s.get("published_at"))
    or datetime.min.replace(tzinfo=timezone.utc),
    reverse=True
)

held_for_review.sort(
    key=lambda s: parse_date(s.get("published_at"))
    or datetime.min.replace(tzinfo=timezone.utc),
    reverse=True
)

# Limit the proposed edition to a manageable editorial shortlist.
shortlist = ready_for_editor[:12]

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

report = {
    "brand": "PixelHive Media",
    "edition": edition,
    "edition_key": edition_key,
    "description": description,
    "generated_at_eat": now.strftime("%Y-%m-%d %H:%M %Z"),
    "status": "DRAFT - NOT PUBLISHED",
    "publication_allowed": False,
    "counts": {
        "input_leads": queue.get("lead_count", len(queue.get("stories", []))),
        "unique_urls": len(stories),
        "editorial_shortlist": len(shortlist),
        "held_for_review": len(held_for_review),
        "older_than_72_hours": len(excluded_old)
    },
    "editorial_shortlist": shortlist,
    "held_for_review": held_for_review,
    "older_than_72_hours": excluded_old,
    "notice": (
        "Headlines are research leads, not verified reporting. "
        "Categorization is keyword-based and may be imperfect. "
        "Verify facts independently, check reuse rights, and write "
        "original copy before publication. No stories are approved "
        "or published by this script."
    )
}

json_path = OUTPUT_DIR / f"{edition_key}-edition-draft.json"
md_path = OUTPUT_DIR / f"{edition_key}-edition-draft.md"

with json_path.open("w", encoding="utf-8") as file:
    json.dump(report, file, ensure_ascii=False, indent=2)

lines = [
    f"# PixelHive Media — {edition}",
    "",
    f"- Generated: {report['generated_at_eat']}",
    f"- Status: {report['status']}",
    f"- Unique URLs: {len(stories)}",
    f"- Shortlist: {len(shortlist)}",
    f"- Held for review: {len(held_for_review)}",
    f"- Older than 72 hours: {len(excluded_old)}",
    "",
    f"> {report['notice']}",
    "",
    "## Editorial shortlist",
    ""
]

if not shortlist:
    lines.append("No leads passed the initial automated screening.")
    lines.append("Review the held-for-review section before selecting stories.")
else:
    for index, story in enumerate(shortlist, start=1):
        lines.extend([
            f"### {index}. [{story['category']}] {story['title']}",
            f"- Source feed: {story.get('source', 'Unknown')}",
            f"- Published: {story.get('published_at') or 'Unknown'}",
            f"- Original link: {story['url']}",
            "- Status: UNVERIFIED — NOT APPROVED",
            ""
        ])

lines.extend(["## Held for human review", ""])
if not held_for_review:
    lines.append("No leads were held by the current screening rules.")
else:
    for story in held_for_review:
        lines.extend([
            f"### {story['title']}",
            f"- Category: {story['category']}",
            f"- Link: {story['url']}",
            "- Review flags: " + "; ".join(story["review_flags"]),
            ""
        ])

lines.extend(["## Older than 72 hours — relevance check", ""])
if not excluded_old:
    lines.append("No older leads were excluded.")
else:
    for story in excluded_old:
        lines.extend([
            f"- [{story['title']}]({story['url']})",
            ""
        ])

with md_path.open("w", encoding="utf-8") as file:
    file.write("\n".join(lines) + "\n")

print(f"Edition: {edition}")
print(f"Shortlist: {len(shortlist)}")
print(f"Held for review: {len(held_for_review)}")
print(f"Older than 72 hours: {len(excluded_old)}")
print(f"Created: {json_path}")
print(f"Created: {md_path}")
print("Draft only. No stories approved or published.")
