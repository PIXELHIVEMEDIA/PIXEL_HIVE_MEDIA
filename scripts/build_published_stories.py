
import json
from pathlib import Path

SOURCE = Path("approved-stories.json")
OUTPUT = Path("scheduled-stories.js")

def main():
    if not SOURCE.exists():
        raise SystemExit("approved-stories.json was not found")

    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if data.get("status") != "approved":
        raise SystemExit("Edition is not approved. Nothing will be published.")

    published = []
    seen = set()

    for story in data.get("stories", []):
        # Approval must be recorded on each story, not just the edition.
        required = [
            "id", "title", "category", "summary",
            "paragraphs", "sourceUrl", "editorialStatus",
            "verifiedBy", "verifiedAt", "publishedAt"
        ]

        if not all(story.get(field) for field in required):
            print("Held for review (missing fields):", story.get("id", "unknown"))
            continue

        if story["editorialStatus"] != "approved":
            print("Held for review:", story["id"])
            continue

        if story["id"] in seen:
            print("Skipped duplicate:", story["id"])
            continue

        if not isinstance(story["paragraphs"], list):
            print("Held: paragraphs must be a list:", story["id"])
            continue

        if not all(isinstance(p, str) and p.strip() for p in story["paragraphs"]):
            print("Held: invalid article paragraphs:", story["id"])
            continue

        item = {
            "id": story["id"],
            "title": story["title"],
            "category": story["category"],
            "summary": story["summary"],
            "paragraphs": story["paragraphs"],
            "sourceUrl": story["sourceUrl"],
            "date": story.get("date", story["publishedAt"][:10]),
            "publishedAt": story["publishedAt"],
            "type": story.get("type", "News"),
            "emoji": story.get("emoji", "🐝"),
            "coverImage": story.get("coverImage", ""),
            "imageAlt": story.get("imageAlt", story["title"]),
            "editorNote": story.get("editorNote", ""),
            "editorialStatus": "approved"
        }

        published.append(item)
        seen.add(item["id"])

    js = "window.PIXELHIVE_SCHEDULED_STORIES = " + json.dumps(
        published, ensure_ascii=False, indent=2
    ) + ";\n"

    OUTPUT.write_text(js, encoding="utf-8")
    print("Published stories prepared:", len(published))
    print("Output:", OUTPUT)

if __name__ == "__main__":
    main()
