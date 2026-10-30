
import os
import re
import json
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

TZ = ZoneInfo("Africa/Nairobi")
now = datetime.now(timezone.utc).astimezone(TZ)

schedule = os.environ.get("SCHEDULE", "")

if schedule == "7 2 * * *":
    edition = "Morning Signal"
elif schedule == "7 10 * * *":
    edition = "The Midday Pulse"
elif schedule == "7 16 * * *":
    edition = "The Evening Wrap"
elif 4 <= now.hour < 10:
    edition = "Morning Signal (manual test)"
elif 10 <= now.hour < 16:
    edition = "The Midday Pulse (manual test)"
else:
    edition = "The Evening Wrap (manual test)"

# These feeds provide research leads only.
# Their presence does not grant permission to republish content.
FEEDS = [
    (
        "BBC Africa",
        "https://feeds.bbci.co.uk/news/world/africa/rss.xml"
    ),
    (
        "BBC World",
        "https://feeds.bbci.co.uk/news/world/rss.xml"
    ),
    (
        "BBC Technology",
        "https://feeds.bbci.co.uk/news/technology/rss.xml"
    ),
]

SENSITIVE_TERMS = [
    "killed", "dead", "death toll", "casualties",
    "rape", "sexual assault", "suicide", "self-harm",
    "terror attack", "hostage", "coup", "election result",
    "fraud allegation", "accused", "alleged",
    "court ruling", "outbreak", "epidemic", "pandemic",
    "war crime", "genocide", "explosion", "mass shooting",
    "abuse", "sanctions", "military strike", "breaking"
]


def clean(value):
    return " ".join(unescape(value or "").split())


def read_text(item, tag):
    node = item.find(tag)
    if node is not None and node.text:
        return clean(node.text)
    return ""


def parse_date(value):
    if not value:
        return None

    try:
        result = parsedate_to_datetime(value)

        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)

        return result.astimezone(timezone.utc)

    except Exception:
        return None


leads = []
feed_errors = []

# Collect headlines and original source links.
for source, url in FEEDS:
    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "PixelHiveEditorialResearch/1.0"
            }
        )

        with urllib.request.urlopen(
            request, timeout=25
        ) as response:
            root = ET.fromstring(response.read())

        items = root.findall(".//item")

        for item in items[:30]:
            title = read_text(item, "title")
            link = read_text(item, "link")
            date_value = read_text(item, "pubDate")
            published = parse_date(date_value)

            if title and link.startswith("https://"):
                leads.append({
                    "title": title,
                    "url": link,
                    "source": source,
                    "published_at": (
                        published.isoformat()
                        if published else None
                    )
                })

    except Exception as error:
        feed_errors.append({
            "source": source,
            "error": type(error).__name__
        })


# Remove exact duplicate URLs.
unique_by_url = {}

for lead in leads:
    url = lead["url"]

    if url not in unique_by_url:
        unique_by_url[url] = {
            **lead,
            "feed_mentions": []
        }

    if lead["source"] not in unique_by_url[url]["feed_mentions"]:
        unique_by_url[url]["feed_mentions"].append(
            lead["source"]
        )

unique_stories = list(unique_by_url.values())

review_stories = []

for story in unique_stories:
    flags = []
    title = story["title"]
    lower_title = title.lower()

    if any(term in lower_title for term in SENSITIVE_TERMS):
        flags.append(
            "Sensitive topic: human review required"
        )

    published = story["published_at"]

    if not published:
        flags.append(
            "Publication date missing: verify freshness"
        )
    else:
        date = datetime.fromisoformat(published)
        age = now.astimezone(timezone.utc) - date

        if age > timedelta(hours=72):
            flags.append(
                "Older than 72 hours: check relevance"
            )

        if age < -timedelta(hours=24):
            flags.append(
                "Future publication date: check feed"
            )

    if len(title) < 20:
        flags.append(
            "Short or media-listing headline: likely exclude"
        )

    if not flags:
        flags.append(
            "Verify independently and check reuse rights"
        )

    story["review_flags"] = flags
    story["status"] = "UNREVIEWED"

    review_stories.append(story)


# Save the research queue.
output = Path("pixelhive-research")
output.mkdir(parents=True, exist_ok=True)

report = {
    "edition": edition,
    "generated_at_eat": now.strftime(
        "%Y-%m-%d %H:%M %Z"
    ),
    "status": "UNREVIEWED - NOT PUBLISHED",
    "lead_count": len(leads),
    "unique_url_count": len(unique_stories),
    "stories": review_stories,
    "feed_errors": feed_errors,
    "policy": (
        "RSS headlines are research leads only. "
        "Feed matching is not fact-checking. "
        "Check independent sources and reuse terms. "
        "Do not copy articles or media without permission."
    )
}

with open(
    output / "review-queue.json",
    "w",
    encoding="utf-8"
) as file:
    json.dump(
        report,
        file,
        ensure_ascii=False,
        indent=2
    )


# Also create a readable Markdown report.
lines = [
    "# PixelHive review queue",
    "",
    f"- Edition: {edition}",
    f"- Generated: {report['generated_at_eat']}",
    f"- Leads collected: {len(leads)}",
    f"- Unique URLs: {len(unique_stories)}",
    "- Status: UNREVIEWED — NOT PUBLISHED",
    "",
    "Verify the facts and source reuse rights before publication.",
    ""
]

for story in review_stories:
    lines.append(f"## {story['title']}")
    lines.append(f"- Feed: {story['source']}")
    lines.append(
        f"- Published: {story['published_at'] or 'Not supplied'}"
    )
    lines.append(f"- Original source: {story['url']}")
    lines.append(
        "- Feeds mentioning URL: "
        + ", ".join(story["feed_mentions"])
    )

    for flag in story["review_flags"]:
        lines.append(f"- Check: {flag}")

    lines.append("")

if feed_errors:
    lines.extend(["## Feed errors", ""])

    for error in feed_errors:
        lines.append(
            f"- {error['source']}: {error['error']}"
        )

with open(
    output / "review-queue.md",
    "w",
    encoding="utf-8"
) as file:
    file.write("\n".join(lines))

print(f"Edition: {edition}")
print(f"Headline leads: {len(leads)}")
print(f"Unique URLs: {len(unique_stories)}")
print("Research queue saved.")
print("Nothing was approved or published.")
