from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "extracted_json"
GROUPED_CSV_PATH = DATA_DIR / "all_items_grouped.csv"
ITEMS_JSON_PATH = DATA_DIR / "cleaned_all_items_summary.json"
MEETINGS_JSON_PATH = DATA_DIR / "all_meetings.json"
ITEMS_BY_MEETING_PATH = DATA_DIR / "items_by_meeting.json"
PDF_DIR = BASE_DIR / "pdfs" / "housing_authority"


FAMILY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Elevators", ("elevator", "lift")),
    ("HVAC", ("hvac", "air conditioner", "air conditioning", "boiler", "chiller", "heating", "cooling", "vent")),
    ("Plumbing / Water", ("pipe", "plumb", "toilet", "sink", "faucet", "shower", "water", "leak", "drain", "sprinkler", "hot water", "tub")),
    ("Laundry", ("washer", "washing machine", "dryer", "laundry")),
    ("Security", ("security", "door", "lock", "camera", "alarm", "intercom", "access")),
    ("Lighting", ("light", "lighting", "bulb", "lamp")),
    ("Pests / Environmental", ("bed bug", "pest", "roach", "mold", "mildew", "asbestos")),
    ("Accessibility", ("ramp", "rail", "handicap", "accessible", "mobility")),
    ("Appliances", ("refrigerator", "fridge", "stove", "oven", "microwave", "dishwasher", "vending")),
    ("Electrical / Power", ("generator", "power", "electrical", "outage", "socket", "switch")),
    ("Exterior / Grounds", ("roof", "window", "floor", "wall", "ceiling", "trash", "dumpster", "parking")),
]


app = Flask(__name__, template_folder="newsapp_templates", static_folder="newsapp_static")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def title_case(value: str | None) -> str:
    if not value:
        return "Other"
    return value.replace("_", " ").strip().title()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def safe_int(value: str | int | None, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def month_key(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m")


def month_label(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%b %Y")
    except ValueError:
        return value


def family_for_item(name: str, category: str | None = None) -> str:
    haystack = f"{name} {category or ''}".lower()
    for family, keywords in FAMILY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return family
    if category:
        return title_case(category)
    return "Other"


def family_slug(value: str) -> str:
    return slugify(value)


def first_text(values: list[str]) -> str:
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned.lower() != "none":
            return cleaned
    return ""


def summarize_meeting(record: dict[str, Any]) -> str:
    pieces: list[str] = []

    residents = record.get("residents_comments", []) or []
    reports = record.get("executive_directors_report", []) or []
    decisions = record.get("decisions", []) or []

    first_resident = first_text([str(entry) for entry in residents])
    first_report = first_text([str(entry) for entry in reports])
    first_decision = first_text([
        entry.get("decision", "") if isinstance(entry, dict) else str(entry)
        for entry in decisions
    ])

    if first_resident:
        pieces.append(first_resident.rstrip("."))
    if first_report:
        pieces.append(first_report.rstrip("."))
    if first_decision:
        pieces.append(first_decision.rstrip("."))

    if pieces:
        return "; ".join(pieces[:3])
    return "No narrative text was extracted for this meeting."


def load_catalog_rows() -> list[dict[str, Any]]:
    if not GROUPED_CSV_PATH.exists():
        return []

    rows: list[dict[str, Any]] = []
    with GROUPED_CSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue

            rows.append(
                {
                    "name": name,
                    "slug": slugify(name),
                    "group": title_case(row.get("category_group")),
                    "count": safe_int(row.get("count")),
                    "first_mentioned_in": (row.get("first_mentioned_in") or "").strip(),
                    "example_note": (row.get("example_note") or "").strip(),
                    "family": family_for_item(name, row.get("category_group")),
                }
            )
    return rows


def load_mentions() -> dict[str, dict[str, Any]]:
    raw_items = load_json_file(ITEMS_JSON_PATH, [])
    items: dict[str, dict[str, Any]] = {}

    for entry in raw_items:
        name = (entry.get("name") or "").strip()
        if not name:
            continue

        mentions: list[dict[str, Any]] = []
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
            "family": family_for_item(name, entry.get("category")),
            "mentions": mentions,
        }

    return items


def build_catalog() -> dict[str, Any]:
    csv_rows = load_catalog_rows()
    mention_lookup = load_mentions()

    items_by_slug: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in csv_rows:
        detailed = mention_lookup.get(row["slug"], {})
        mentions = detailed.get("mentions", [])
        count = max(row["count"], safe_int(detailed.get("count")), len(mentions))
        family = detailed.get("family") or row["family"]
        group = row["group"]

        mention_dates = [mention["date_sort"] for mention in mentions if mention["date_sort"]]
        first_seen = min(mention_dates).strftime("%b %d, %Y") if mention_dates else row["first_mentioned_in"]
        last_seen = max(mention_dates).strftime("%b %d, %Y") if mention_dates else row["first_mentioned_in"]

        item = {
            "name": row["name"],
            "slug": row["slug"],
            "group": group,
            "family": family,
            "count": count,
            "first_mentioned_in": row["first_mentioned_in"],
            "first_seen": first_seen,
            "last_seen": last_seen,
            "example_note": row["example_note"],
            "mentions": mentions,
            "summary": build_summary(row["name"], count, mentions, row["example_note"]),
        }

        items_by_slug[row["slug"]] = item
        groups[group].append(item)

    for group_items in groups.values():
        group_items.sort(key=lambda item: (-item["count"], item["name"].lower()))

    return {
        "items_by_slug": items_by_slug,
        "groups": [
            {
                "name": group_name,
                "slug": slugify(group_name),
                "items": group_items,
                "count": sum(item["count"] for item in group_items),
            }
            for group_name, group_items in sorted(groups.items(), key=lambda pair: pair[0].lower())
        ],
        "all_items": sorted(items_by_slug.values(), key=lambda item: (-item["count"], item["name"].lower())),
    }


def build_summary(name: str, count: int, mentions: list[dict[str, Any]], fallback_note: str) -> str:
    if mentions:
        date_values = [mention["date"] for mention in mentions if mention["date"]]
        date_range = f"from {date_values[0]} to {date_values[-1]}" if len(date_values) > 1 else f"on {date_values[0]}"
        snippets = [mention["notes"] for mention in mentions if mention["notes"]]
        sample_notes = "; ".join(snippets[:3]) if snippets else fallback_note
        if sample_notes:
            return f"{name.title()} appears in meeting records {date_range}. Notes: {sample_notes}"
        return f"{name.title()} appears in meeting records {date_range}."

    if fallback_note:
        return f"{name.title()} appears in meeting records. Example note: {fallback_note}"
    return f"{name.title()} appears in the meeting records."


def load_meeting_records() -> list[dict[str, Any]]:
    return load_json_file(MEETINGS_JSON_PATH, [])


def load_items_by_meeting() -> dict[str, dict[str, Any]]:
    raw_rows = load_json_file(ITEMS_BY_MEETING_PATH, [])
    return {row.get("filename"): row for row in raw_rows if row.get("filename")}


def meeting_slug(filename: str) -> str:
    return slugify(filename.replace(".pdf", ""))


def build_meetings() -> list[dict[str, Any]]:
    items_by_meeting = load_items_by_meeting()
    meetings: list[dict[str, Any]] = []

    for meeting in load_meeting_records():
        filename = (meeting.get("filename") or "").strip()
        date_value = (meeting.get("date") or "").strip()
        date_sort = parse_date(date_value)
        meeting_items = items_by_meeting.get(filename, {}).get("items", []) or []

        item_names: list[str] = []
        item_slugs: list[str] = []
        family_counts: Counter[str] = Counter()
        for item in meeting_items:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            item_names.append(name)
            item_slug = slugify(name)
            item_slugs.append(item_slug)
            family_counts[family_for_item(name, item.get("category"))] += 1

        meetings.append(
            {
                "filename": filename,
                "slug": meeting_slug(filename),
                "date": date_value,
                "date_sort": date_sort,
                "summary": summarize_meeting(meeting),
                "residents_comments": meeting.get("residents_comments", []) or [],
                "executive_directors_report": meeting.get("executive_directors_report", []) or [],
                "decisions": meeting.get("decisions", []) or [],
                "items": meeting_items,
                "item_names": item_names,
                "item_slugs": sorted(set(item_slugs)),
                "family_counts": family_counts,
                "item_count": len(item_names),
                "resident_count": len([entry for entry in meeting.get("residents_comments", []) or [] if str(entry).strip() and str(entry).strip().lower() != "none"]),
                "decision_count": len([entry for entry in meeting.get("decisions", []) or [] if str(entry).strip()]),
            }
        )

    meetings.sort(key=lambda item: item["date_sort"] or datetime.min)
    return meetings


def build_timeline(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    monthly_family_counts: dict[str, Counter[str]] = defaultdict(Counter)
    monthly_totals: Counter[str] = Counter()

    for item in items:
        family = item.get("family") or family_for_item(item.get("name", ""), item.get("group"))
        for mention in item.get("mentions", []):
            bucket = month_key(mention.get("date_sort"))
            if not bucket:
                continue
            monthly_family_counts[bucket][family] += 1
            monthly_totals[bucket] += 1

    timeline: list[dict[str, Any]] = []
    for bucket in sorted(monthly_totals.keys()):
        family_counts = monthly_family_counts[bucket]
        timeline.append(
            {
                "key": bucket,
                "label": month_label(bucket),
                "count": monthly_totals[bucket],
                "family_counts": dict(family_counts),
                "top_families": [
                    {"family": family, "count": count}
                    for family, count in family_counts.most_common(4)
                ],
            }
        )
    return timeline


def build_relationships(meetings: list[dict[str, Any]]) -> dict[str, Any]:
    family_pairs: Counter[tuple[str, str]] = Counter()
    item_pairs: Counter[tuple[str, str]] = Counter()
    related_items: dict[str, Counter[str]] = defaultdict(Counter)

    for meeting in meetings:
        family_names = sorted(
            set(
                family_for_item(item.get("name", ""), item.get("category"))
                for item in meeting.get("items", [])
                if item.get("name")
            )
        )
        for left, right in combinations(family_names, 2):
            family_pairs[(left, right)] += 1

        item_slugs = sorted(set(meeting.get("item_slugs", [])))
        for left, right in combinations(item_slugs, 2):
            item_pairs[(left, right)] += 1
            related_items[left][right] += 1
            related_items[right][left] += 1

    return {
        "top_family_pairs": [
            {"source": left, "target": right, "count": count}
            for (left, right), count in family_pairs.most_common(16)
        ],
        "top_item_pairs": [
            {"source": left, "target": right, "count": count}
            for (left, right), count in item_pairs.most_common(24)
        ],
        "related_items": related_items,
    }


def build_dashboard(catalog: dict[str, Any], meetings: list[dict[str, Any]]) -> dict[str, Any]:
    all_items = catalog["all_items"]
    timeline = build_timeline(all_items)
    relationships = build_relationships(meetings)

    family_counts: Counter[str] = Counter()
    family_months: defaultdict[str, set[str]] = defaultdict(set)
    for item in all_items:
        family = item.get("family") or family_for_item(item["name"], item.get("group"))
        family_counts[family] += item["count"]
        for mention in item.get("mentions", []):
            bucket = month_key(mention.get("date_sort"))
            if bucket:
                family_months[family].add(bucket)

    top_families = [
        {
            "family": family,
            "slug": family_slug(family),
            "count": count,
            "month_count": len(family_months[family]),
        }
        for family, count in family_counts.most_common(12)
    ]

    year_counts: Counter[str] = Counter()
    for row in timeline:
        year_counts[row["key"][:4]] += row["count"]

    recent_meetings = sorted(meetings, key=lambda item: item["date_sort"] or datetime.min, reverse=True)[:8]

    return {
        "top_families": top_families,
        "timeline": timeline,
        "relationships": relationships,
        "recent_meetings": recent_meetings,
        "year_counts": dict(sorted(year_counts.items())),
        "total_meetings": len(meetings),
        "timeline_labels": [row["label"] for row in timeline],
        "timeline_counts": [row["count"] for row in timeline],
    }


def normalize_search_terms(query: str) -> list[str]:
    return [token for token in re.split(r"\s+", query.lower().strip()) if token]


def search_items(items: list[dict[str, Any]], query: str, family_filter: str = "") -> list[dict[str, Any]]:
    tokens = normalize_search_terms(query)
    family_filter = family_filter.strip().lower()
    if not tokens and not family_filter:
        return items

    results: list[dict[str, Any]] = []
    for item in items:
        haystack = " ".join(
            [
                item["name"],
                item["group"],
                item["family"],
                item["summary"],
                item["example_note"],
                item["first_mentioned_in"],
            ]
        ).lower()
        if family_filter and item["family"].lower() != family_filter:
            continue
        if all(token in haystack for token in tokens):
            results.append(item)
    return results


def search_meetings(meetings: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    tokens = normalize_search_terms(query)
    if not tokens:
        return []

    matches: list[dict[str, Any]] = []
    for meeting in meetings:
        haystack = " ".join(
            [
                meeting["filename"],
                meeting["date"],
                meeting["summary"],
                " ".join(meeting.get("residents_comments", [])),
                " ".join(meeting.get("executive_directors_report", [])),
                " ".join(
                    decision.get("decision", "") if isinstance(decision, dict) else str(decision)
                    for decision in meeting.get("decisions", [])
                ),
            ]
        ).lower()
        if all(token in haystack for token in tokens):
            matches.append(meeting)
    return matches


def exact_item_match(items: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    normalized = query.strip().lower()
    if not normalized:
        return None

    query_slug = slugify(query)
    for item in items:
        if normalized == item["name"].lower() or query_slug == item["slug"]:
            return item
    return None


def exact_meeting_match(meetings: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    normalized = query.strip().lower()
    if not normalized:
        return None

    query_slug = slugify(query)
    for meeting in meetings:
        if normalized == meeting["filename"].lower() or normalized == meeting["date"].lower() or query_slug == meeting["slug"]:
            return meeting
    return None


def exact_family_match(families: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    normalized = query.strip().lower()
    if not normalized:
        return None

    query_slug = family_slug(query)
    for family in families:
        if normalized == family["family"].lower() or query_slug == family["slug"]:
            return family
    return None


def monthly_series_for_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    monthly_counts: Counter[str] = Counter()
    for mention in item.get("mentions", []):
        bucket = month_key(mention.get("date_sort"))
        if bucket:
            monthly_counts[bucket] += 1
    return [
        {"label": month_label(bucket), "value": count}
        for bucket, count in sorted(monthly_counts.items())
    ]


def yearly_series_for_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    yearly_counts: Counter[str] = Counter()
    for mention in item.get("mentions", []):
        date_sort = mention.get("date_sort")
        if date_sort:
            yearly_counts[date_sort.strftime("%Y")] += 1
    return [
        {"label": year, "value": count}
        for year, count in sorted(yearly_counts.items())
    ]


def monthly_series_for_family(items: list[dict[str, Any]], family_name: str) -> list[dict[str, Any]]:
    monthly_counts: Counter[str] = Counter()
    for item in items:
        if item.get("family") != family_name:
            continue
        for mention in item.get("mentions", []):
            bucket = month_key(mention.get("date_sort"))
            if bucket:
                monthly_counts[bucket] += 1
    return [
        {"label": month_label(bucket), "value": count}
        for bucket, count in sorted(monthly_counts.items())
    ]


def build_related_items(slug: str, relationships: dict[str, Any], catalog: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    pairs = relationships["related_items"].get(slug, Counter())
    related: list[dict[str, Any]] = []
    for related_slug, count in pairs.most_common(limit):
        item = catalog["items_by_slug"].get(related_slug)
        if not item:
            continue
        related.append({**item, "related_count": count})
    return related


CATALOG = build_catalog()
MEETINGS = build_meetings()
DASHBOARD = build_dashboard(CATALOG, MEETINGS)
FAMILY_INDEX = sorted({item["family"] for item in CATALOG["all_items"]})


@app.route("/")
def index() -> str:
    query = request.args.get("q", "").strip()
    family = request.args.get("family", "").strip()

    exact_item = exact_item_match(CATALOG["all_items"], query)
    if exact_item:
        return redirect(url_for("item_detail", slug=exact_item["slug"]))

    exact_meeting = exact_meeting_match(MEETINGS, query)
    if exact_meeting:
        return redirect(url_for("meeting_detail", slug=exact_meeting["slug"]))

    exact_family = exact_family_match(
        [{"family": name, "slug": family_slug(name)} for name in FAMILY_INDEX],
        query or family,
    )
    if exact_family and not query:
        return redirect(url_for("family_detail", slug=exact_family["slug"]))

    filtered_items = search_items(CATALOG["all_items"], query, family)
    filtered_meetings = search_meetings(MEETINGS, query)

    if family and not query:
        family_label = next((name for name in FAMILY_INDEX if family_slug(name) == family.lower()), family)
        filtered_items = [item for item in CATALOG["all_items"] if family_slug(item["family"]) == family.lower()]
        filtered_meetings = [meeting for meeting in MEETINGS if any(family_for_item(item.get("name", ""), item.get("category")) == family_label for item in meeting.get("items", []))]

    grouped_items: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in filtered_items:
        grouped_items[item["group"]].append(item)

    visible_groups: list[dict[str, Any]] = []
    for group in CATALOG["groups"]:
        items = grouped_items.get(group["name"], []) if query or family else group["items"]
        if not items:
            continue
        visible_groups.append({**group, "items": items, "count": sum(item["count"] for item in items)})

    return render_template(
        "index.html",
        query=query,
        family=family,
        family_index=FAMILY_INDEX,
        groups=visible_groups,
        search_results=filtered_items[:24],
        search_meetings=filtered_meetings[:10],
        result_count=len(filtered_items),
        meeting_count=len(filtered_meetings),
        total_items=len(CATALOG["all_items"]),
        total_mentions=sum(item["count"] for item in CATALOG["all_items"]),
        dashboard=DASHBOARD,
    )


@app.route("/item/<slug>")
def item_detail(slug: str) -> str:
    item = CATALOG["items_by_slug"].get(slug)
    if not item:
        abort(404)

    all_items = CATALOG["all_items"]
    current_index = next((index for index, candidate in enumerate(all_items) if candidate["slug"] == slug), None)
    previous_item = all_items[current_index - 1] if current_index and current_index > 0 else None
    next_item = all_items[current_index + 1] if current_index is not None and current_index < len(all_items) - 1 else None

    meeting_refs = []
    seen_meetings = set()
    for mention in item.get("mentions", []):
        filename = mention.get("filename")
        if not filename or filename in seen_meetings:
            continue
        seen_meetings.add(filename)
        meeting_slug_value = meeting_slug(filename)
        meeting = next((entry for entry in MEETINGS if entry["slug"] == meeting_slug_value), None)
        if meeting:
            meeting_refs.append(meeting)

    related_items = build_related_items(slug, DASHBOARD["relationships"], CATALOG)

    return render_template(
        "item.html",
        item=item,
        related_items=related_items,
        meeting_refs=meeting_refs[:8],
        previous_item=previous_item,
        next_item=next_item,
        monthly_series=monthly_series_for_item(item),
        yearly_series=yearly_series_for_item(item),
        item_url=url_for("item_detail", slug=slug),
    )


@app.route("/family/<slug>")
def family_detail(slug: str) -> str:
    family_name = next((name for name in FAMILY_INDEX if family_slug(name) == slug), None)
    if not family_name:
        abort(404)

    family_items = [item for item in CATALOG["all_items"] if item["family"] == family_name]
    family_items.sort(key=lambda item: (-item["count"], item["name"].lower()))
    family_series = monthly_series_for_family(CATALOG["all_items"], family_name)

    related_families: Counter[str] = Counter()
    for pair in DASHBOARD["relationships"]["top_family_pairs"]:
        if pair["source"] == family_name:
            related_families[pair["target"]] += pair["count"]
        elif pair["target"] == family_name:
            related_families[pair["source"]] += pair["count"]

    top_related = [
        {"family": name, "slug": family_slug(name), "count": count}
        for name, count in related_families.most_common(8)
    ]

    return render_template(
        "family.html",
        family_name=family_name,
        family_slug=slug,
        family_items=family_items,
        family_series=family_series,
        related_families=top_related,
        dashboard=DASHBOARD,
    )


@app.route("/meetings")
def meetings_index() -> str:
    meetings = sorted(MEETINGS, key=lambda item: item["date_sort"] or datetime.min, reverse=True)
    return render_template("meetings.html", meetings=meetings, dashboard=DASHBOARD)


@app.route("/meeting/<slug>")
def meeting_detail(slug: str) -> str:
    meeting = next((entry for entry in MEETINGS if entry["slug"] == slug), None)
    if not meeting:
        abort(404)

    related_items = [
        {"name": CATALOG["items_by_slug"][related_slug]["name"], "slug": related_slug, "count": count}
        for related_slug, count in Counter(meeting.get("item_slugs", [])).most_common()
        if related_slug in CATALOG["items_by_slug"]
    ]

    family_summary = [
        {"family": family, "count": count}
        for family, count in meeting["family_counts"].most_common()
    ]

    return render_template(
        "meeting.html",
        meeting=meeting,
        related_items=related_items,
        family_summary=family_summary,
        dashboard=DASHBOARD,
    )


@app.route("/pdf/<path:filename>")
def pdf_file(filename: str):
    if not PDF_DIR.exists():
        abort(404)
    return send_from_directory(PDF_DIR, filename)


def main() -> None:
    app.run(debug=True, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()
