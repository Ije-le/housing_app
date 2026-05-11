from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable


DEFAULT_GROUPED_CSV = Path("./extracted_json/all_items_grouped.csv")
DEFAULT_MEETINGS_JSON = Path("./extracted_json/all_meetings.json")
DEFAULT_OUTPUT_JSON = Path("./extracted_json/cleaned_all_items_summary.json")
DEFAULT_OUTPUT_CSV = Path("./extracted_json/cleaned_all_items_summary.csv")
DEFAULT_ITEMS_BY_MEETING = Path("./extracted_json/cleaned_items_by_meeting.json")

# Manual aliases for grouped labels that appear with different wording in minutes.
ITEM_ALIASES: dict[str, list[str]] = {
    "air conditioner": ["ac unit", "hvac unit", "air conditioning"],
    "bait": ["bed bug", "pest control", "wildlife control", "wildlife"],
    "bully boards": ["bulletin board", "bulletin boards"],
    "grab bar": ["grab bars", "handrail", "rail"],
    "handicapped bathroom unit": ["handicap bathroom", "bathroom unit"],
    "handicapped parking enforcement": ["parking permit", "parking enforcement", "handicapped parking"],
    "hot water": ["water heater", "water bill"],
    "leader training": ["leadership training"],
    "lock": ["locks", "door lock"],
    "pest treatment": ["pest control"],
    "plumbing fixtues": ["plumbing fixtures", "plumbing"],
    "radiator": ["radiators", "heater", "heating"],
    "radiators": ["radiator", "heaters", "heating"],
    "rail": ["handrail", "grab bar", "rails"],
    "regrant": ["grant", "ross grant"],
    "sink": ["sinks", "faucet", "faucets"],
    "training expenses": ["training travel expenses", "training"],
    "trash dumpster": ["dumpster", "trash united", "trash chute"],
    "vacuum": ["resident cleaner", "cleaner"],
    "vent": ["vents", "ventilation", "hvac"],
    "ventilation": ["vent", "vents", "hvac"],
    "vents": ["vent", "ventilation", "hvac"],
    "wildlife control": ["wildlife", "pest control"],
    "windows": ["window"],
    "curbside produce services": ["curbside produce", "curbside fresh produce", "mobile services shop"],
}


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def normalize_category(value: str) -> str:
    value = (value or "").strip().lower()
    value = value.replace("/", "_")
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "other"


def title_case(value: str) -> str:
    if not value:
        return "Other"
    return value.replace("_", " ").strip().title()


def safe_date_sort(value: str) -> tuple[int, str]:
    if not value:
        return (99999999, "")

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return (int(dt.strftime("%Y%m%d")), value)
        except ValueError:
            continue

    return (99999999, value)


def load_allowlist(grouped_csv: Path) -> dict[str, dict[str, str]]:
    allowlist: dict[str, dict[str, str]] = {}
    with grouped_csv.open(newline="", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue

            key = normalize_name(name)
            allowlist[key] = {
                "name": name,
                "category": normalize_category(row.get("category_group") or row.get("category") or "other"),
            }

    return allowlist


def load_meetings(meetings_json: Path) -> list[dict]:
    with meetings_json.open(encoding="utf-8") as file_handle:
        meetings = json.load(file_handle)

    if not isinstance(meetings, list):
        raise ValueError(f"Expected a JSON list in {meetings_json}")

    return meetings


def collect_text_sources(meeting: dict) -> list[str]:
    parts: list[str] = []

    raw_text = meeting.get("raw_text")
    if isinstance(raw_text, str) and raw_text.strip():
        parts.append(raw_text)

    for key in ("residents_comments", "executive_directors_report", "decisions", "attendees"):
        value = meeting.get(key)
        if isinstance(value, list):
            lines = [str(item).strip() for item in value if str(item).strip()]
            if lines:
                parts.append("\n".join(lines))
        elif isinstance(value, str) and value.strip():
            parts.append(value)

    return parts


def split_sentences(text: str) -> list[str]:
    candidates: list[str] = []
    for block in re.split(r"\n+", text):
        block = re.sub(r"\s+", " ", block).strip()
        if not block:
            continue
        pieces = re.split(r"(?<=[.!?])\s+", block)
        for piece in pieces:
            piece = piece.strip()
            if piece:
                candidates.append(piece)
    return candidates


def item_name_variants(item_name: str) -> list[str]:
    """Generate conservative variants for OCR/noise-tolerant matching."""
    base = normalize_name(item_name)
    if not base:
        return []

    variants: set[str] = {base}

    for alias in ITEM_ALIASES.get(base, []):
        alias_norm = normalize_name(alias)
        if alias_norm:
            variants.add(alias_norm)

    # Split combined terms like "faucets/sinks" and match each piece too.
    pieces = [p.strip() for p in re.split(r"[/,;|]+", base) if p.strip()]
    variants.update(pieces)

    # Handle simple plural/singular forms.
    for term in list(variants):
        words = term.split()
        if not words:
            continue
        last = words[-1]
        if last.endswith("s") and len(last) > 3:
            variants.add(" ".join(words[:-1] + [last[:-1]]))
        elif not last.endswith("s"):
            variants.add(" ".join(words[:-1] + [last + "s"]))

    # Common report-style suffixes in grouped labels.
    for term in list(variants):
        if term.endswith(" report"):
            variants.add(term.replace(" report", ""))
        if term.endswith(" system"):
            variants.add(term.replace(" system", ""))

    return sorted(v for v in variants if v)


def build_patterns(item_name: str) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for variant in item_name_variants(item_name):
        escaped = re.escape(variant)
        escaped = escaped.replace(r"\ ", r"\s+")
        patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
    return patterns


def extract_mentions(item_name: str, meeting: dict) -> list[str]:
    patterns = build_patterns(item_name)
    snippets: list[str] = []

    for source_text in collect_text_sources(meeting):
        for sentence in split_sentences(source_text):
            if any(pattern.search(sentence) for pattern in patterns):
                cleaned = re.sub(r"\s+", " ", sentence).strip()
                if cleaned and cleaned not in snippets:
                    snippets.append(cleaned)

    return snippets


def rebuild_summary(
    allowlist: dict[str, dict[str, str]],
    meetings: list[dict],
) -> tuple[list[dict], list[dict]]:
    items_by_name: dict[str, dict] = {}
    items_by_meeting: list[dict] = []

    for meeting in meetings:
        filename = str(meeting.get("filename") or "").strip()
        date = str(meeting.get("date") or "").strip()
        meeting_items: list[dict] = []

        for item_key, item_meta in allowlist.items():
            snippets = extract_mentions(item_meta["name"], meeting)
            if not snippets:
                continue

            notes = " | ".join(snippets)
            meeting_items.append(
                {
                    "name": item_meta["name"],
                    "category": item_meta["category"],
                    "notes": notes,
                }
            )

            item_record = items_by_name.setdefault(
                item_key,
                {
                    "name": item_meta["name"],
                    "category": item_meta["category"],
                    "count": 0,
                    "mentions": [],
                },
            )

            item_record["count"] += 1
            item_record["mentions"].append(
                {
                    "filename": filename,
                    "date": date,
                    "notes": notes,
                }
            )

        if meeting_items:
            items_by_meeting.append(
                {
                    "filename": filename,
                    "date": date,
                    "items": meeting_items,
                }
            )

    summary = sorted(items_by_name.values(), key=lambda item: (-item["count"], item["name"].lower()))
    for item in summary:
        item["mentions"] = sorted(item["mentions"], key=lambda mention: safe_date_sort(mention.get("date", "")))

    items_by_meeting.sort(key=lambda meeting: safe_date_sort(str(meeting.get("date") or "")))
    return summary, items_by_meeting


def write_csv_exports(summary: Iterable[dict], summary_csv: Path) -> None:
    with summary_csv.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.writer(file_handle)
        writer.writerow(["name", "category", "count", "first_mentioned_in", "example_note"])
        for item in summary:
            first_mention = item["mentions"][0] if item.get("mentions") else {}
            writer.writerow(
                [
                    item.get("name", ""),
                    item.get("category", "other"),
                    item.get("count", 0),
                    first_mention.get("filename", ""),
                    first_mention.get("notes", ""),
                ]
            )


def write_grouped_csv(summary: Iterable[dict], grouped_csv: Path) -> None:
    with grouped_csv.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.writer(file_handle)
        writer.writerow(["category_group", "name", "count", "first_mentioned_in", "example_note"])
        for item in summary:
            first_mention = item["mentions"][0] if item.get("mentions") else {}
            writer.writerow(
                [
                    title_case(item.get("category", "other")),
                    item.get("name", ""),
                    item.get("count", 0),
                    first_mention.get("filename", ""),
                    first_mention.get("notes", ""),
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild cleaned item summaries from meeting JSON.")
    parser.add_argument("--grouped-csv", type=Path, default=DEFAULT_GROUPED_CSV)
    parser.add_argument("--meetings-json", type=Path, default=DEFAULT_MEETINGS_JSON)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--items-by-meeting", type=Path, default=DEFAULT_ITEMS_BY_MEETING)
    args = parser.parse_args()

    allowlist = load_allowlist(args.grouped_csv)
    meetings = load_meetings(args.meetings_json)

    summary, items_by_meeting = rebuild_summary(allowlist, meetings)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.items_by_meeting.parent.mkdir(parents=True, exist_ok=True)

    args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    args.items_by_meeting.write_text(json.dumps(items_by_meeting, indent=2), encoding="utf-8")
    write_csv_exports(summary, args.output_csv)
    write_grouped_csv(summary, args.grouped_csv.parent / "cleaned_all_items_grouped.csv")

    print(f"Wrote {len(summary)} items to {args.output_json}")
    print(f"Wrote {len(items_by_meeting)} meetings to {args.items_by_meeting}")
    print(f"Wrote CSV summary to {args.output_csv}")


if __name__ == "__main__":
    main()
