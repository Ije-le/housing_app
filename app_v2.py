#!/usr/bin/env python3
"""
Facility Inspector App v2
Interactive exploration of building maintenance issues from 5 years of meeting minutes.
"""

from flask import Flask, render_template, request, jsonify
from markupsafe import Markup
from pathlib import Path
import csv
import json
import re
from datetime import datetime
from collections import defaultdict
from flask import send_from_directory, url_for, abort

app = Flask(__name__)

# Data files
GROUPED_ITEMS_PATH = Path("./extracted_json/grouped_items.csv")
ITEMS_MENTIONS_PATH = Path("./extracted_json/items_with_mentions.csv")
ALL_MEETINGS_PATH = Path("./extracted_json/all_meetings.json")
MANUAL_BLURBS_PATH = Path("./manual_blurbs.json")
PDFS_DIR = Path("./pdfs")

# Load data
def load_grouped_items():
    """Load items grouped by category."""
    items_by_category = defaultdict(list)
    
    with open(GROUPED_ITEMS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row.get("category", "Other")
            example_snippet = row.get("example_snippet", "").strip()
            # Clean snippet delimiters
            example_snippet = example_snippet.replace(" | ", ", ").replace("|", ",")
            example_snippet = " ".join(example_snippet.split())
            
            items_by_category[category].append({
                "name": row.get("name", "").strip(),
                "canonical": row.get("canonical", "").strip(),
                "count": int(row.get("count", 0)),
                "first_mentioned_filename": row.get("first_mentioned_filename", "").strip(),
                "first_mentioned_date": row.get("first_mentioned_date", "").strip(),
                "example_snippet": example_snippet,
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
                snippet = row.get("mention_snippet", "").strip()
                # Clean snippet delimiters
                snippet = snippet.replace(" | ", ", ").replace("|", ",")
                snippet = " ".join(snippet.split())
                
                mentions.append({
                    "date": row.get("mention_date", "").strip(),
                    "filename": row.get("mention_filename", "").strip(),
                    "snippet": snippet,
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

def load_manual_blurbs():
    """Load manually edited blurbs from JSON file."""
    if MANUAL_BLURBS_PATH.exists():
        try:
            with open(MANUAL_BLURBS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_manual_blurbs(blurbs):
    """Save blurbs to JSON file for manual editing."""
    with open(MANUAL_BLURBS_PATH, "w", encoding="utf-8") as f:
        json.dump(blurbs, f, indent=2, ensure_ascii=False)

def export_all_blurbs():
    """Export all auto-generated blurbs to JSON file for manual editing."""
    blurbs = {}
    
    for category, items in GROUPED_ITEMS.items():
        for item in items:
            # Load mentions for this item
            mentions = load_item_mentions(item["canonical"])
            # Generate blurb
            blurb = generate_item_summary(item, mentions)
            # Store with canonical name as key
            blurbs[item["canonical"]] = str(blurb)
    
    save_manual_blurbs(blurbs)
    return blurbs

def extract_kwic_mentions(item_name, mentions):
    """Extract contextually relevant mentions using KWIC (Key Word In Context).
    
    Filters mentions to only include those with meaningful action/context:
    - Scheduling/planning actions
    - Completion/resolution
    - Problems/failures
    - Status updates
    - Confirmation of work done
    """
    # Keywords indicating meaningful context
    action_keywords = {
        'scheduled', 'schedule', 'planned', 'plan', 'completed', 'complete', 
        'finished', 'done', 'approved', 'approve', 'failed', 'failure', 'problem',
        'issue', 'broken', 'not working', 'fixed', 'fix', 'repair', 'repaired',
        'maintenance', 'maintain', 'inspection', 'inspect', 'checked', 'check',
        'replacement', 'replace', 'need', 'needed', 'urgent', 'delay', 'delayed',
        'postpone', 'postponed', 'confirmed', 'confirm', 'awaiting', 'await',
        'pending', 'in progress', 'not yet', 'still', 'remains', 'remain',
        'payment', 'payments', 'paid', 'bill', 'invoice', 'grant', 'funding',
        'reinstall', 'installed', 'installation', 'alarm', 'fire', 'smoke',
        'inspection', 'passed', 'pass', 'requested', 'request', 'announce',
        'announcement', 'department', 'emergency'
    }
    
    kwic_mentions = []
    
    for mention in mentions:
        if not mention["snippet"]:
            continue
        
        snippet_lower = mention["snippet"].lower()
        item_lower = item_name.lower()
        
        # Check if snippet contains action keywords nearby the item name
        contains_action = any(keyword in snippet_lower for keyword in action_keywords)
        
        if contains_action:
            kwic_mentions.append(mention)
    
    return kwic_mentions

def format_date_short(date_str):
    """Format date as 'Month Year' (e.g., 'March 2022')."""
    if not date_str or date_str == "Unknown Date":
        return "an unknown date"
    
    formats = ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%B %Y")
        except ValueError:
            continue
    
    return date_str

def extract_action_context(snippet, mention_type):
    """Extract specific action/context from snippet for narrative."""
    snippet_lower = snippet.lower()
    snippet_clean = snippet.strip()
    
    # Look for specific outcomes and include details
    if mention_type == 'incident':
        # For incidents, show the full context to capture what happened
        return snippet_clean
    elif 'scheduled' in snippet_lower or 'schedule' in snippet_lower:
        return snippet_clean
    elif 'completed' in snippet_lower or 'done' in snippet_lower:
        return snippet_clean
    elif 'confirmed' in snippet_lower or 'confirm' in snippet_lower:
        return snippet_clean
    elif 'theft' in snippet_lower or 'stolen' in snippet_lower or 'missing' in snippet_lower:
        return snippet_clean
    elif 'not working' in snippet_lower or 'broken' in snippet_lower or 'failed' in snippet_lower:
        return snippet_clean
    elif 'problem' in snippet_lower or 'issue' in snippet_lower:
        # Return the full snippet to include problem details
        return snippet_clean
    elif 'delay' in snippet_lower or 'postpone' in snippet_lower:
        return snippet_clean
    elif 'awaiting' in snippet_lower or 'pending' in snippet_lower:
        return snippet_clean
    else:
        # Return full snippet without truncation
        return snippet_clean

def categorize_mention_type(snippet, item_name):
    """Categorize the type of mention for narrative building."""
    snippet_lower = snippet.lower()
    item_lower = item_name.lower()
    
    # Check for incidents first (highest priority)
    if any(word in snippet_lower for word in ['fire', 'outbreak', 'incident', 'emergency', 'called', 'call', 'smoke', 'theft', 'stolen']):
        return 'incident'
    elif any(word in snippet_lower for word in ['scheduled', 'schedule', 'planned', 'plan']):
        return 'scheduled'
    elif any(word in snippet_lower for word in ['completed', 'complete', 'finished', 'done', 'confirmed', 'confirm']):
        return 'completed'
    elif any(word in snippet_lower for word in ['failed', 'failure', 'problem', 'not working', 'broken']):
        return 'problem'
    elif any(word in snippet_lower for word in ['awaiting', 'await', 'pending', 'not yet', 'delay', 'delayed']):
        return 'pending'
    else:
        return 'mention'

def build_event_signature(text, item_name):
    """Create a normalized signature to deduplicate repeated events."""
    text_lower = (text or "").lower()
    item_tokens = {t for t in re.findall(r"[a-z0-9']+", item_name.lower()) if len(t) > 2}
    stop_words = {
        'the', 'and', 'for', 'with', 'from', 'that', 'this', 'were', 'was', 'are', 'is',
        'has', 'have', 'had', 'been', 'into', 'onto', 'over', 'under', 'their', 'there',
        'after', 'before', 'about', 'through', 'during', 'when', 'where', 'which', 'while',
        'meeting', 'board', 'residents', 'resident', 'tower', 'towers', 'unit', 'property',
        'attick', 'systems', 'system'
    }

    tokens = []
    for token in re.findall(r"[a-z0-9']+", text_lower):
        if len(token) <= 2:
            continue
        if token in stop_words or token in item_tokens:
            continue
        if token.isdigit():
            continue
        tokens.append(token)

    if not tokens:
        return text_lower.strip()

    # Keep ordered unique tokens so near-duplicate incidents collapse.
    ordered_unique = list(dict.fromkeys(tokens))
    return " ".join(ordered_unique[:16])

def generate_item_summary(item_data, mentions):
    """Generate a three-part narrative summary of an item's timeline."""
    if not mentions:
        return Markup(f"{item_data['name']} was mentioned {item_data['count']} time(s) in the meeting records.")

    mentions_sorted = sorted(mentions, key=lambda x: parse_date_for_sort(x["date"]))

    if len(mentions_sorted) == 1:
        only = mentions_sorted[0]
        date_str = format_date_short(only["date"])
        snippet = " ".join((only["snippet"] or "").split()).strip(" .")
        summary = f"{item_data['name']} was mentioned once, in {date_str}: {snippet}."
        summary += f" <a href='#' onclick='toggleTimeline(event)' class='view-timeline-link'>View full timeline →</a>"
        return Markup(summary)

    first = mentions_sorted[0]
    last = mentions_sorted[-1]
    middle = mentions_sorted[1:-1]

    # --- Opening sentence: first chronological mention ---
    first_date = format_date_short(first["date"])
    first_snippet = " ".join((first["snippet"] or "").split()).strip(" .")
    opening = f"In {first_date}, {first_snippet}."

    # --- "Most recently" sentence: last mention ---
    last_snippet = " ".join((last["snippet"] or "").split()).strip(" .")
    last_date = format_date_short(last["date"])
    closing = f"Most recently, in {last_date}, {last_snippet}."

    # --- "Since then" paragraph: deduplicated middle events ---
    # Build signatures for first and last so we don't echo them in the middle
    first_sig = build_event_signature(first_snippet, item_data["name"])
    last_sig = build_event_signature(last_snippet, item_data["name"])

    seen_signatures = {first_sig, last_sig}
    middle_events = []

    for mention in middle:
        snippet = " ".join((mention["snippet"] or "").split()).strip(" .")
        if not snippet:
            continue
        sig = build_event_signature(snippet, item_data["name"])
        if not sig or sig in seen_signatures:
            continue
        seen_signatures.add(sig)
        middle_events.append(snippet)

    if middle_events:
        since_then = "Since then, " + "; ".join(middle_events) + "."
        summary = f"{opening} {since_then} {closing}"
    else:
        # No meaningful middle — just open and close
        summary = f"{opening} {closing}"

    summary += f" <a href='#' onclick='toggleTimeline(event)' class='view-timeline-link'>View full timeline →</a>"
    return Markup(summary)


# Load data at startup
GROUPED_ITEMS = load_grouped_items()
CATEGORIES = sorted(GROUPED_ITEMS.keys())

# Export blurbs on first run if manual_blurbs.json doesn't exist
if not MANUAL_BLURBS_PATH.exists():
    print(f"Generating manual_blurbs.json for the first time...")
    try:
        export_all_blurbs()
        print(f"✓ Created {MANUAL_BLURBS_PATH}")
    except Exception as e:
        print(f"✗ Error exporting blurbs: {e}")

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
    
    # Sort by mention count (highest first), then by name for consistent ordering
    category_stats.sort(key=lambda x: (-x["mention_count"], x["name"]))
    
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


@app.route("/category-breakdown")
def category_breakdown():
    """Category break down: list all items grouped by category with links to details."""
    # Build a flattened list of all items and sort by mention count (highest first)
    full_items = []
    for items in GROUPED_ITEMS.values():
        for it in items:
            full_items.append(it)

    full_items_sorted = sorted(full_items, key=lambda x: (-x["count"], x["name"].lower()))

    return render_template(
        "category_breakdown.html",
        full_items=full_items_sorted,
    )


@app.route('/pdfs/<path:filename>')
def pdf_file(filename):
    """Serve PDF files from the local `pdfs/` directory so timeline links open the source document."""
    # Protect against directory traversal by using send_from_directory
    # First try direct path under PDFS_DIR
    candidate = PDFS_DIR / filename
    if candidate.exists():
        return send_from_directory(str(PDFS_DIR), filename)

    # If not found, search recursively for a matching filename in subdirectories
    # This allows CSVs to reference filenames without including subfolder names.
    for p in PDFS_DIR.rglob('*'):
        if p.is_file() and p.name == Path(filename).name:
            rel_path = p.relative_to(PDFS_DIR)
            return send_from_directory(str(PDFS_DIR), str(rel_path))

    # Not found
    abort(404)

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
    
    # Load manual blurb if it exists, otherwise generate one
    manual_blurbs = load_manual_blurbs()
    if item_canonical in manual_blurbs:
        summary = Markup(manual_blurbs[item_canonical])
    else:
        summary = generate_item_summary(item_data, mentions)
    #summary = generate_item_summary(item_data, mentions)
    
    # Calculate total mentions in system for proportion
    total_system_mentions = sum(sum(item["count"] for item in items) for items in GROUPED_ITEMS.values())
    item_proportion = (len(mentions) / total_system_mentions * 100) if total_system_mentions > 0 else 0
    
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
        total_system_mentions=total_system_mentions,
        item_proportion=item_proportion,
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

@app.route("/admin/export-blurbs")
def admin_export_blurbs():
    """Export all auto-generated blurbs to JSON file for manual editing."""
    try:
        blurbs = export_all_blurbs()
        return jsonify({
            "status": "success",
            "message": f"Exported {len(blurbs)} blurbs to {MANUAL_BLURBS_PATH}",
            "file": str(MANUAL_BLURBS_PATH)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.template_filter("slugify")
def slugify(text):
    """Convert text to URL-safe slug."""
    return text.lower().replace(" ", "-").replace("/", "-")

if __name__ == "__main__":
    app.run(debug=True, port=5001)
