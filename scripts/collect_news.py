
import json
import re
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

OUTPUT_DIR = Path("pixelhive-research")
JSON_FILE = OUTPUT_DIR / "review-queue.json"
MD_FILE = OUTPUT_DIR / "review-queue.md"

FEEDS = [
    {
        "name": "BBC Africa",
        "url": "https://feeds.bbci.co.uk/news/world/africa/rss.xml",
        "category": "Africa",
    },
    {
        "name": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "World",
    },
    {
        "name": "BBC Technology",
        "url": "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "category": "Technology",
    },
]

SENSITIVE_TERMS = [
    "election", "president", "politician", "parliament",
    "government", "minister", "political", "campaign",
    "war", "attack", "terror", "terrorist", "killed",
    "death", "fatal", "injured", "rape", "sexual assault",
    "child abuse", "suicide", "self-harm", "court ruling",
    "arrested", "accused", "allegation", "corruption",
    "fraud", "medical emergency", "disease outbreak",
]


def clean_text(value):
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def get_text(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return clean_text(found.text)
    return ""


def fetch_feed(feed):
    request = urllib.request.Request(
        feed["url"],
        headers={"User-Agent": "PixelHiveMedia-NewsResearch/1.0"},
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        raw = response.read()

    root = ET.fromstring(raw)
    items = root.findall(".//item")

    if not items:
        # Support Atom feeds as well as RSS feeds.
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    results = []

    for item in items[:35]:
        title = get_text(item, ["title", "{http://www.w3.org/2005/Atom}title"])
        link = get_text(item, ["link"])

        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = atom_link.attrib.get("href", "")

        summary = get_text(
            item,
            ["description", "summary",
             "{http://www.w3.org/2005/Atom}summary"],
        )

        published = get_text(
            item,
            ["pubDate", "published", "updated",
             "{http://www.w3.org/2005/Atom}published",
             "{http://www.w3.org/2005/Atom}updated"],
        )

        if not title or not link.startswith(("https://", "http://")):
            continue

        text_to_check = (title + " " + summary).lower()
        flags = [
            term for term in SENSITIVE_TERMS
            if term in text_to_check
        ]

        results.append({
            "title": title,
            "url": link,
            "summary": summary[:1200],
            "source": feed["name"],
            "category": feed["category"],
            "publishedAt": published,
            "sensitiveTopicFlags": flags,
            "editorialStatus": "review",
            "verified": False,
            "publicationStatus": "not_published",
            "collectedAt": datetime.now(timezone.utc).isoformat(),
        })

    return results


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    collected = []
    feed_errors = []

    for feed in FEEDS:
        try:
            entries = fetch_feed(feed)
            collected.extend(entries)
            print(f'{feed["name"]}: collected {len(entries)} leads')
        except (urllib.error.URLError, TimeoutError, ET.ParseError,
                OSError, ValueError) as error:
            message = f'{feed["name"]}: {error}'
            feed_errors.append(message)
            print(f"WARNING: Could not read feed: {message}")

    unique = []
    seen_urls = set()

    for entry in collected:
        url = entry["url"].split("#", 1)[0].strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            entry["url"] = url
            unique.append(entry)

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Research leads for human editorial review only",
        "publicationEnabled": False,
        "totalLeads": len(unique),
        "feedErrors": feed_errors,
        "stories": unique,
    }

    JSON_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# PixelHive Media — Research Review Queue",
        "",
        f'Generated: {payload["generatedAt"]}',
        f'Total unique leads: {len(unique)}',
        "",
        "**IMPORTANT:** These are research leads, not verified or published stories.",
        "A human editor must verify claims, check context, and approve publication.",
        "",
    ]

    for index, story in enumerate(unique, start=1):
        lines.extend([
            f'## {index}. {story["title"]}',
            "",
            f'- Category: {story["category"]}',
            f'- Source: {story["source"]}',
            f'- Published: {story["publishedAt"] or "Not provided"}',
            f'- Review status: {story["editorialStatus"]}',
            f'- Sensitive-topic flags: {", ".join(story["sensitiveTopicFlags"]) or "None detected"}',
            f'- Source link: {story["url"]}',
            "",
            story["summary"] or "No summary supplied by the feed.",
            "",
            "---",
            "",
        ])

    if feed_errors:
        lines.extend(["## Feed warnings", ""])
        lines.extend(f"- {error}" for error in feed_errors)

    MD_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Saved research queue: {JSON_FILE}")
    print(f"Saved readable review list: {MD_FILE}")
    print("No stories were published.")

    if not unique:
        print("WARNING: No leads collected. Check feed availability.")
        # Do not fail the workflow just because an RSS feed is unavailable.
        # The saved queue still records the errors.
    else:
        print(f"SUCCESS: {len(unique)} unique research leads are ready for review.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: Research collection failed: {error}", file=sys.stderr)
        raise
