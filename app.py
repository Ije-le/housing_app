from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for


BASE_DIR = Path(__file__).resolve().parent
GROUPED_CSV_PATH = BASE_DIR / "extracted_json" / "all_items_grouped.csv"
ITEMS_JSON_PATH = BASE_DIR / "extracted_json" / "cleaned_all_items_summary.json"
PDF_DIR = BASE_DIR / "pdfs" / "housing_authority"


app = Flask(__name__)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def title_case(value: str | None) -> str:
    if not value:
        return "Other"
    return value.replace("_", " ").strip().title()


def safe_int(value: str | int | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def load_csv_rows() -> list[dict[str, Any]]:
    if not GROUPED_CSV_PATH.exists():
        return []

    rows: list[dict[str, Any]] = []
    with GROUPED_CSV_PATH.open(newline="", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        for row in reader:
            item_name = (row.get("name") or "").strip()
            if not item_name:
                continue

            rows.append(
                {
                    "name": item_name,
                    "slug": slugify(item_name),
                    "group": title_case(row.get("category_group")),
                    "count": safe_int(row.get("count")),
                    "first_mentioned_in": (row.get("first_mentioned_in") or "").strip(),
                    "example_note": (row.get("example_note") or "").strip(),
                }
            )

    return rows


def load_mentions() -> dict[str, dict[str, Any]]:
    if not ITEMS_JSON_PATH.exists():
        return {}

    with ITEMS_JSON_PATH.open(encoding="utf-8") as file_handle:
        raw_items = json.load(file_handle)

    items: dict[str, dict[str, Any]] = {}
    for entry in raw_items:
        name = (entry.get("name") or "").strip()
        if not name:
            continue

        mentions = []
        for mention in entry.get("mentions", []):
            mention_date = (mention.get("date") or "").strip()
            mentions.append(
                {
                    "filename": (mention.get("filename") or "").strip(),
                    "date": mention_date,
                    "notes": (mention.get("notes") or "").strip(),
                    "date_sort": parse_date(mention_date),
                }
            )

        mentions.sort(key=lambda item: item["date_sort"] or datetime.min)

        items[slugify(name)] = {
            "name": name,
            "count": safe_int(entry.get("count")),
            "category": title_case(entry.get("category")),
            "mentions": mentions,
        }

    return items


def build_summary(name: str, count: int, mentions: list[dict[str, Any]], fallback_note: str) -> str:
    if mentions:
        dates = [mention["date"] for mention in mentions if mention["date"]]
        date_range = f"from {dates[0]} to {dates[-1]}" if len(dates) > 1 else f"on {dates[0]}"
        snippets = [mention["notes"] for mention in mentions if mention["notes"]]
        sample_notes = "; ".join(snippets[:3]) if snippets else fallback_note
        if sample_notes:
            return f"{name.title()} appears in meeting records {date_range}. Notes: {sample_notes}"
        return f"{name.title()} appears in meeting records {date_range}."

    if fallback_note:
        return f"{name.title()} appears in meeting records. Example note: {fallback_note}"

    return f"{name.title()} appears in the meeting records."


def build_catalog() -> dict[str, Any]:
    csv_rows = load_csv_rows()
    mention_lookup = load_mentions()

    items_by_slug: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in csv_rows:
        detailed = mention_lookup.get(row["slug"], {})
        mentions = detailed.get("mentions", [])
        count = max(row["count"], safe_int(detailed.get("count")), len(mentions))
        group_name = row["group"]

        item = {
            "name": row["name"],
            "slug": row["slug"],
            "group": group_name,
            "count": count,
            "first_mentioned_in": row["first_mentioned_in"],
            "example_note": row["example_note"],
            "mentions": mentions,
            "summary": build_summary(row["name"], count, mentions, row["example_note"]),
        }

        items_by_slug[row["slug"]] = item
        groups[group_name].append(item)

    for group_items in groups.values():
        group_items.sort(key=lambda item: (-item["count"], item["name"].lower()))

    group_rows = [
        {
            "name": group_name,
            "slug": slugify(group_name),
            "items": group_items,
            "count": sum(item["count"] for item in group_items),
        }
        for group_name, group_items in sorted(groups.items(), key=lambda pair: pair[0].lower())
    ]

    return {
        "items_by_slug": items_by_slug,
        "groups": group_rows,
        "all_items": sorted(items_by_slug.values(), key=lambda item: (-item["count"], item["name"].lower())),
    }


def search_items(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    normalized = query.strip().lower()
    if not normalized:
        return items

    matches: list[dict[str, Any]] = []
    for item in items:
        haystack = " ".join(
            [
                item["name"],
                item["group"],
                item["summary"],
                item["example_note"],
                item["first_mentioned_in"],
            ]
        ).lower()
        if normalized in haystack:
            matches.append(item)

    return matches


def exact_item_match(items: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    normalized = query.strip().lower()
    if not normalized:
        return None

    query_slug = slugify(query)
    for item in items:
        if normalized == item["name"].strip().lower() or query_slug == item["slug"]:
            return item

    return None


@app.route("/pdf/<path:filename>")
def pdf_file(filename: str):
    if not PDF_DIR.exists():
        abort(404)
    return send_from_directory(PDF_DIR, filename)


CATALOG = build_catalog()


@app.route("/")
def index() -> str:
    query = request.args.get("q", "").strip()
    all_items = CATALOG["all_items"]
    exact_match = exact_item_match(all_items, query)
    if exact_match:
        return redirect(url_for("item_detail", slug=exact_match["slug"]))

    filtered_items = search_items(all_items, query)

    grouped_matches: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in filtered_items:
        grouped_matches[item["group"]].append(item)

    visible_groups = []
    for group in CATALOG["groups"]:
        if query:
            items = grouped_matches.get(group["name"], [])
        else:
            items = group["items"]

        if not items:
            continue

        visible_groups.append(
            {
                **group,
                "items": items,
                "count": sum(item["count"] for item in items),
            }
        )

    return render_template(
        "index.html",
        query=query,
        groups=visible_groups,
        search_results=filtered_items,
        total_items=len(all_items),
        total_mentions=sum(item["count"] for item in all_items),
        result_count=len(filtered_items),
    )


@app.route("/item/<slug>")
def item_detail(slug: str) -> str:
    item = CATALOG["items_by_slug"].get(slug)
    if not item:
        abort(404)

    previous_item = None
    next_item = None
    all_items = CATALOG["all_items"]
    current_index = next((index for index, candidate in enumerate(all_items) if candidate["slug"] == slug), None)
    if current_index is not None:
        if current_index > 0:
            previous_item = all_items[current_index - 1]
        if current_index < len(all_items) - 1:
            next_item = all_items[current_index + 1]

    return render_template(
        "detail.html",
        item=item,
        previous_item=previous_item,
        next_item=next_item,
        item_url=url_for("item_detail", slug=slug),
    )


if __name__ == "__main__":
    app.run(debug=True)