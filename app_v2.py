#!/usr/bin/env python3
"""
Housing Authority Accountability App v2
Interactive exploration of building maintenance issues from 5 years of meeting minutes.
"""

from flask import Flask, render_template, request, jsonify
from pathlib import Path
import csv
import json
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)

# Data files
GROUPED_ITEMS_PATH = Path("./extracted_json/grouped_items.csv")
ITEMS_MENTIONS_PATH = Path("./extracted_json/items_with_mentions.csv")
ALL_MEETINGS_PATH = Path("./extracted_json/all_meetings.json")

# Load data
def load_grouped_items():
    """Load items grouped by category."""
    items_by_category = defaultdict(list)
    
    with open(GROUPED_ITEMS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row.get("category", "Other")
            items_by_category[category].append({
                "name": row.get("name", "").strip(),
                "canonical": row.get("canonical", "").strip(),
                "count": int(row.get("count", 0)),
                "first_mentioned_filename": row.get("first_mentioned_filename", "").strip(),
                "first_mentioned_date": row.get("first_mentioned_date", "").strip(),
                "example_snippet": row.get("example_snippet", "").strip(),
            })
    
    # Sort items within each category by count (descending)
    for category in items_by_category:
        items_by_category[category].sort(key=lambda x: (-x["count"], x["name"].lower()))
    
    return dict(items_by_category)

def load_item_mentions(canonical_name):
    """Load all mentions for a specific item."""
    mentions = []
    
    with open(ITEMS_MENTIONS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("canonical", "").strip().lower() == canonical_name.lower():
                mentions.append({
                    "date": row.get("mention_date", "").strip(),
                    "filename": row.get("mention_filename", "").strip(),
                    "snippet": row.get("mention_snippet", "").strip(),
                })
    
    # Sort by date (earliest first)
    mentions.sort(key=lambda x: parse_date_for_sort(x["date"]))
    
    return mentions

def parse_date_for_sort(date_str):
    """Parse date string for sorting."""
    if not date_str or date_str == "Unknown Date":
        return datetime.min
    
    formats = ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return datetime.min

def generate_item_summary(item_data, mentions):
    """Generate a narrative summary for an item."""
    if not mentions:
        return f"{item_data['name']} was mentioned {item_data['count']} time(s) in the meeting records."
    
    dates = [m["date"] for m in mentions if m["date"] and m["date"] != "Unknown Date"]
    if len(dates) > 1:
        date_range = f"from {dates[0]} to {dates[-1]}"
    elif dates:
        date_range = f"on {dates[0]}"
    else:
        date_range = "in the meeting records"
    
    # Get sample snippets
    snippets = [m["snippet"] for m in mentions if m["snippet"]][:3]
    
    summary = f"{item_data['name'].title()} appears in meeting records {date_range}. "
    summary += f"Mentioned {item_data['count']} times. "
    
    if snippets:
        summary += "Examples: " + "; ".join(snippets)
    
    return summary

# Load data at startup
GROUPED_ITEMS = load_grouped_items()
CATEGORIES = sorted(GROUPED_ITEMS.keys())

@app.route("/")
def index():
    """Home page: overview of all categories and their issue counts."""
    category_stats = []
    
    for category in CATEGORIES:
        items = GROUPED_ITEMS[category]
        total_mentions = sum(item["count"] for item in items)
        
        category_stats.append({
            "name": category,
            "item_count": len(items),
            "mention_count": total_mentions,
        })
    
    return render_template(
        "index_v2.html",
        category_stats=category_stats,
        total_unique_items=sum(len(items) for items in GROUPED_ITEMS.values()),
        total_mentions=sum(sum(item["count"] for item in items) for items in GROUPED_ITEMS.values()),
    )

@app.route("/category/<category_name>")
def category_detail(category_name):
    """Category page: show all items in this category with mention counts."""
    # Find matching category (case-insensitive)
    matching_category = None
    for cat in CATEGORIES:
        if cat.lower() == category_name.lower():
            matching_category = cat
            break
    
    if not matching_category:
        return "Category not found", 404
    
    items = GROUPED_ITEMS[matching_category]
    total_mentions = sum(item["count"] for item in items)
    
    return render_template(
        "category_v2.html",
        category=matching_category,
        items=items,
        total_mentions=total_mentions,
    )

@app.route("/item/<item_canonical>")
def item_detail(item_canonical):
    """Item detail page: show full timeline and pattern analysis."""
    # Find item in grouped items to get metadata
    item_data = None
    category = None
    
    for cat, items in GROUPED_ITEMS.items():
        for item in items:
            if item["canonical"].lower() == item_canonical.lower():
                item_data = item
                category = cat
                break
    
    if not item_data:
        return "Item not found", 404
    
    # Load all mentions for this item
    mentions = load_item_mentions(item_canonical)
    
    # Generate summary
    summary = generate_item_summary(item_data, mentions)
    
    # Calculate frequency stats
    mentions_by_year = defaultdict(int)
    for mention in mentions:
        date_str = mention["date"]
        try:
            year = datetime.strptime(date_str, "%B %d, %Y").year
            mentions_by_year[year] += 1
        except:
            pass
    
    return render_template(
        "item_v2.html",
        item_name=item_data["name"],
        item_canonical=item_canonical,
        category=category,
        summary=summary,
        mentions=mentions,
        mention_count=len(mentions),
        total_count=item_data["count"],
        first_mentioned_date=item_data["first_mentioned_date"],
        example_snippet=item_data["example_snippet"],
        mentions_by_year=dict(sorted(mentions_by_year.items())),
    )

@app.route("/api/related-issues/<item_canonical>")
def api_related_issues(item_canonical):
    """API endpoint: find issues mentioned around the same time (potential patterns)."""
    # Load all meetings
    with open(ALL_MEETINGS_PATH, encoding="utf-8") as f:
        meetings = json.load(f)
    
    # Find meetings where this item was mentioned
    related_items = defaultdict(int)
    
    for meeting in meetings:
        meeting_text = " ".join(
            meeting.get("residents_comments", []) +
            meeting.get("executive_directors_report", []) +
            meeting.get("decisions", [])
        ).lower()
        
        if item_canonical.lower() in meeting_text:
            # This meeting mentions our item
            # Now find other items mentioned in same meeting
            for cat, items in GROUPED_ITEMS.items():
                for item in items:
                    if item["canonical"].lower() != item_canonical.lower():
                        if item["canonical"].lower() in meeting_text:
                            related_items[item["name"]] += 1
    
    # Return top related items
    top_related = sorted(
        related_items.items(),
        key=lambda x: -x[1]
    )[:5]
    
    return jsonify([
        {"name": name, "co_mentions": count}
        for name, count in top_related
    ])

@app.template_filter("slugify")
def slugify(text):
    """Convert text to URL-safe slug."""
    return text.lower().replace(" ", "-").replace("/", "-")

if __name__ == "__main__":
    app.run(debug=True, port=5001)
