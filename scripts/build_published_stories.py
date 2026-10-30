
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
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def valid_story_id(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{2,99}", value)
        is not None
    )


def main():
    if not SOURCE.exists():
        raise SystemExit("approved-stories.json was not found.")

    try:
        data = json.loads(SOURCE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Could not read approval file: {exc}")

    stories = data.get("stories", [])
    if not isinstance(stories, list):
        raise SystemExit("'stories' must be a JSON array.")

    published = []
    seen = set()

    if data.get("status") == "approved":
        for story in stories:
            if not isinstance(story, dict):
                print("Held: invalid story object.")
                continue

            story_id = story.get("id", "unknown")

            required = [
                "id", "title", "category", "summary", "paragraphs",
                "sourceUrl", "editorialStatus", "verifiedBy",
                "verifiedAt", "publishedAt"
            ]
            missing = [
                key for key in required
                if key not in story
                or story[key] is None
                or story[key] == ""
            ]

            if missing:
                print(f"Held {story_id}: missing {', '.join(missing)}")
                continue

            if story["editorialStatus"] != "approved":
                print(f"Held for editorial review: {story_id}")
                continue

            if not valid_story_id(story["id"]):
                print(f"Held: invalid ID: {story_id}")
                continue

            if story["id"] in seen:
                print(f"Skipped duplicate ID: {story_id}")
                continue

            if not all(
                isinstance(story[key], str) and story[key].strip()
                for key in ("title", "category", "summary", "verifiedBy")
            ):
                print(f"Held: empty or invalid text field: {story_id}")
                continue

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
                print(f"Held: invalid paragraphs: {story_id}")
                continue

            image = story.get("coverImage", "")
            if image and not valid_http_url(image):
                print(f"Held: invalid image URL: {story_id}")
                continue

            published.append({
                "id": story["id"],
                "title": story["title"].strip(),
                "category": story["category"].strip(),
                "summary": story["summary"].strip(),
                "paragraphs": paragraphs,
                "sourceUrl": story["sourceUrl"].strip(),
                "date": story.get("date", story["publishedAt"][:10]),
                "publishedAt": story["publishedAt"],
                "type": story.get("type", "News"),
                "emoji": story.get("emoji", "🐝"),
                "coverImage": image,
                "imageAlt": story.get("imageAlt", story["title"]),
                "imageCredit": story.get("imageCredit", ""),
                "editorNote": story.get("editorNote", ""),
                "editorialStatus": "approved"
            })
            seen.add(story["id"])
    else:
        print("Edition is not approved. No stories will be published.")

    OUTPUT.write_text(
        "window.PIXELHIVE_SCHEDULED_STORIES = "
        + json.dumps(published, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8"
    )

    print(f"Approved stories prepared: {len(published)}")
    print(f"Generated file: {OUTPUT}")


if __name__ == "__main__":
    main()
