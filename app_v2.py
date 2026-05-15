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
    # Convert slug back to original category name
    # category_name comes as slug (e.g. "accessibility-and-safety-features")
    # Need to match against actual category names
    matching_category = None
    for cat in CATEGORIES:
        # Slugify both sides for comparison
        if slugify(cat) == category_name.lower():
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
    """API endpoint: find related issues with temporal analysis.
    
    Returns items that:
    1. Appear in same meetings (co_mentions count)
    2. Have temporal relationships (one typically appears after the other)
    """
    # Load all meetings and item mentions
    with open(ALL_MEETINGS_PATH, encoding="utf-8") as f:
        meetings = json.load(f)
    
    # Get mentions for the current item
    current_item_mentions = load_item_mentions(item_canonical)
    if not current_item_mentions:
        return jsonify([])
    
    current_first_date = parse_date_for_sort(current_item_mentions[0]["date"])
    current_last_date = parse_date_for_sort(current_item_mentions[-1]["date"])
    
    # Track relationships for all other items
    related_analysis = {}
    
    for cat, items in GROUPED_ITEMS.items():
        for item in items:
            if item["canonical"].lower() == item_canonical.lower():
                continue
            
            # Load all mentions for this candidate item
            other_mentions = load_item_mentions(item["canonical"])
            if not other_mentions:
                continue
            
            other_first_date = parse_date_for_sort(other_mentions[0]["date"])
            other_last_date = parse_date_for_sort(other_mentions[-1]["date"])
            
            # Count same-meeting occurrences
            co_mention_count = 0
            for meeting in meetings:
                meeting_text = " ".join(
                    meeting.get("residents_comments", []) +
                    meeting.get("executive_directors_report", []) +
                    meeting.get("decisions", [])
                ).lower()
                
                if (item_canonical.lower() in meeting_text and 
                    item["canonical"].lower() in meeting_text):
                    co_mention_count += 1
            
            # Calculate temporal gap
            if current_first_date != datetime.min and other_first_date != datetime.min:
                time_gap = abs((other_first_date - current_first_date).days)
                months_apart = round(time_gap / 30, 1)
                
                # Determine pattern type
                if other_first_date > current_first_date:
                    pattern = f"typically appears {months_apart} months later"
                    time_offset = months_apart
                elif other_first_date < current_first_date:
                    pattern = f"typically appears {months_apart} months before"
                    time_offset = -months_apart
                else:
                    pattern = "appears around the same time"
                    time_offset = 0
                
                # Only include if there's a meaningful connection
                if co_mention_count > 0 or time_gap < 365:  # Same meetings or within 1 year
                    related_analysis[item["canonical"]] = {
                        "name": item["name"],
                        "co_mentions": co_mention_count,
                        "months_apart": time_offset,
                        "pattern": pattern,
                        "first_mention_date": other_mentions[0]["date"],
                    }
    
    # Sort by: (1) co-mentions count, (2) time gap proximity
    sorted_related = sorted(
        related_analysis.items(),
        key=lambda x: (-x[1]["co_mentions"], abs(x[1]["months_apart"]))
    )[:8]  # Return top 8 related items
    
    return jsonify([
        {
            "name": data["name"],
            "co_mentions": data["co_mentions"],
            "months_apart": data["months_apart"],
            "pattern": data["pattern"],
            "first_mention_date": data["first_mention_date"],
        }
        for _, data in sorted_related
    ])

@app.template_filter("slugify")
def slugify(text):
    """Convert text to URL-safe slug."""
    return text.lower().replace(" ", "-").replace("/", "-")

if __name__ == "__main__":
    app.run(debug=True, port=5001)
