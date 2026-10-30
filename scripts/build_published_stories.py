
import json
import re
from pathlib import Path
from urllib.parse import urlparse

INPUT_FILE = Path("approved-stories.json")
OUTPUT_FILE = Path("scheduled-stories.js")

SENSITIVE_TERMS = (
    "election", "president", "politician", "parliament",
    "government", "minister", "war", "attack", "terror",
    "killed", "death", "rape", "sexual assault", "suicide",
    "child abuse", "corruption", "fraud", "accused",
    "allegation", "arrested", "court ruling",
)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def valid_http_url(value):
    if not nonempty(value):
        return False
    try:
        parsed = urlparse(value.strip())
        return (
            parsed.scheme in ("https", "http")
            and bool(parsed.netloc)
        )
    except ValueError:
        return False


def story_is_sensitive(story):
    text = " ".join([
        str(story.get("title", "")),
        str(story.get("summary", "")),
        str(story.get("category", "")),
        " ".join(story.get("paragraphs", []))
        if isinstance(story.get("paragraphs"), list) else "",
    ]).lower()

    flags = story.get("sensitiveTopicFlags", [])
    flagged = isinstance(flags, list) and len(flags) > 0

    return flagged or any(term in text for term in SENSITIVE_TERMS)


def valid_story(story):
    if not isinstance(story, dict):
        return False, "Story must be a JSON object"

    required_fields = (
        "id", "title", "summary", "category",
        "reviewer", "verifiedAt", "sourceUrl",
    )

    for field in required_fields:
        if not nonempty(story.get(field)):
            return False, f"Missing required field: {field}"

    if not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", story["id"]
    ):
        return False, "Story ID must use lowercase letters, numbers and hyphens"

    if story.get("editorialStatus") != "approved":
        return False, "Story is not explicitly approved"

    if story.get("verified") is not True:
        return False, "Story is not marked verified"

    if not valid_http_url(story.get("sourceUrl")):
        return False, "A valid source URL is required"

    if not nonempty(story.get("reviewer")):
        return False, "A named reviewer is required"

    if not nonempty(story.get("verifiedAt")):
        return False, "A verification timestamp is required"

    paragraphs = story.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        return False, "At least one article paragraph is required"

    if not all(nonempty(p) for p in paragraphs):
        return False, "Every article paragraph must contain text"

    image_url = story.get("coverImage") or story.get("imageUrl")
    if not valid_http_url(image_url):
        return False, "A valid, reviewed cover image URL is required"

    if story_is_sensitive(story):
        if story.get("additionalReview") is not True:
            return False, "Sensitive story needs additional review"
        if not nonempty(story.get("additionalReviewer")):
            return False, "Sensitive story needs a second named reviewer"

    return True, "Approved for website output"


def main():
    if not INPUT_FILE.exists():
        raise SystemExit(f"Missing required file: {INPUT_FILE}")

    try:
        data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in {INPUT_FILE}: {error}")

    if not isinstance(data, dict):
        raise SystemExit("The edition file must contain a JSON object")

    stories = data.get("stories", [])
    if not isinstance(stories, list):
        raise SystemExit("'stories' must be a JSON array")

    approved = []
    rejected = []
    seen_ids = set()

    if data.get("status") != "approved":
        print("Edition status is not approved. No stories published.")
    else:
        for original in stories:
            ok, reason = valid_story(original)

            if ok and original["id"] in seen_ids:
                ok, reason = False, "Duplicate story ID"

            if not ok:
                title = (
                    original.get("title", "(untitled)")
                    if isinstance(original, dict)
                    else "(invalid story)"
                )
                rejected.append({"title": title, "reason": reason})
                continue

            story = dict(original)

            # Existing website pages use coverImage.
            # Accept imageUrl as an alternative input field.
            story["coverImage"] = (
                story.get("coverImage") or story.get("imageUrl")
            )

            # Give the existing website a safe default image description.
            if not nonempty(story.get("imageAlt")):
                story["imageAlt"] = story["title"]

            seen_ids.add(story["id"])
            approved.append(story)

    javascript = (
        "/* Generated automatically. Do not edit directly. */\n"
        "window.PIXELHIVE_SCHEDULED_STORIES = "
        + json.dumps(approved, ensure_ascii=False, indent=2)
        + ";\n"
    )

    OUTPUT_FILE.write_text(javascript, encoding="utf-8")

    print(f"Approved stories generated: {len(approved)}")

    if rejected:
        print("Stories withheld from the website:")
        for item in rejected:
            print(f'- {item["title"]}: {item["reason"]}')

    print(f"Generated {OUTPUT_FILE}")
    print("Human fact-checking and image-rights checks are still required.")


if __name__ == "__main__":
    main()
