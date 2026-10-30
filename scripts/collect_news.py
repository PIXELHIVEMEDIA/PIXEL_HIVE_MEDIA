
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

SOURCE = Path("approved-stories.json")
OUTPUT = Path("scheduled-stories.js")


def valid_http_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError:
        return False


def valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def valid_story_id(value):
    return isinstance(value, str) and re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}", value
    ) is not None


def main():
    if not SOURCE.exists():
        raise SystemExit(
            "approved-stories.json was not found. No stories published."
        )

    try:
        data = json.loads(SOURCE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Could not read approval file: {exc}")

    if data.get("status") != "approved":
        raise SystemExit(
            "The edition is not approved. No stories published."
        )

    source_stories = data.get("stories", [])
    if not isinstance(source_stories, list):
        raise SystemExit("'stories' must be a JSON array.")

    published = []
    seen = set()

    for story in source_stories:
        if not isinstance(story, dict):
            print("Held: story entry is not an object.")
            continue

        story_id = story.get("id", "unknown")

        required = [
            "id",
            "title",
            "category",
            "summary",
            "paragraphs",
            "sourceUrl",
            "editorialStatus",
            "verifiedBy",
            "verifiedAt",
            "publishedAt",
        ]

        missing = [
            field for field in required
            if field not in story
            or story[field] is None
            or story[field] == ""
        ]

        if missing:
            print(
                f"Held for review: {story_id}; missing: "
                + ", ".join(missing)
            )
            continue

        if story["editorialStatus"] != "approved":
            print(f"Held for review: {story_id}")
            continue

        if not valid_story_id(story["id"]):
            print(f"Held: invalid story ID: {story_id}")
            continue

        if story["id"] in seen:
            print(f"Skipped duplicate ID: {story_id}")
            continue

        for field in ("title", "category", "summary", "verifiedBy"):
            if not isinstance(story[field], str) or not story[field].strip():
                print(f"Held: invalid {field}: {story_id}")
                break
        else:
            if not valid_http_url(story["sourceUrl"]):
                print(f"Held: invalid source URL: {story_id}")
                continue

            if not valid_timestamp(story["verifiedAt"]):
                print(f"Held: invalid verification timestamp: {story_id}")
                continue

            if not valid_timestamp(story["publishedAt"]):
                print(f"Held: invalid publication timestamp: {story_id}")
                continue

            paragraphs = story["paragraphs"]
            if (
                not isinstance(paragraphs, list)
                or not paragraphs
                or not all(
                    isinstance(p, str) and p.strip()
                    for p in paragraphs
                )
            ):
                print(f"Held: invalid article paragraphs: {story_id}")
                continue

            image = story.get("coverImage", "")
            if image and not valid_http_url(image):
                print(f"Held: invalid image URL: {story_id}")
                continue

            item = {
                "id": story["id"],
                "title": story["title"].strip(),
                "category": story["category"].strip(),
                "summary": story["summary"].strip(),
                "paragraphs": paragraphs,
                "sourceUrl": story["sourceUrl"].strip(),
                "date": story.get(
                    "date", story["publishedAt"][:10]
                ),
                "publishedAt": story["publishedAt"],
                "type": story.get("type", "News"),
                "emoji": story.get("emoji", "🐝"),
                "coverImage": image,
                "imageAlt": story.get(
                    "imageAlt", story["title"]
                ),
                "editorNote": story.get("editorNote", ""),
                "editorialStatus": "approved",
            }

            published.append(item)
            seen.add(story["id"])

    # The file appends approved stories to the existing library.
    # index.html and story.html can continue using stories.js unchanged.
    js = (
        "\n/* Generated by PixelHive's approval workflow. */\n"
        "window.PIXELHIVE_STORIES = "
        "(Array.isArray(window.PIXELHIVE_STORIES) "
        "? window.PIXELHIVE_STORIES : []).concat("
        + json.dumps(published, ensure_ascii=False, indent=2)
        + ");\n"
    )

    OUTPUT.write_text(js, encoding="utf-8")
    print(f"Approved stories added to generated file: {len(published)}")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
