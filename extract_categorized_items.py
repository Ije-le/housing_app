#!/usr/bin/env python3
"""
Extract housing items from all_meetings.json using Claude API.

Uses Claude to intelligently extract and categorize items from meeting minutes.
Outputs CSV files ready for the app.
"""

import json
import csv
import subprocess
import argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any

# Categories for classification
CATEGORIES = [
    "Big Equipment",
    "Small Equipment",
    "Appliances",
    "Wall Openings",
    "Services",
    "HVAC",
    "Accessibility and safety features",
    "Electrical",
    "Plumbing",
    "Other"
]

def load_meetings(path: Path) -> list:
    """Load all_meetings.json."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_items_from_meeting_with_claude(meeting: dict, model: str) -> List[Dict[str, str]]:
    """Use Claude to extract and categorize items from a meeting."""
    text_parts = []
    
    for key in ("residents_comments", "executive_directors_report", "decisions"):
        value = meeting.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    text_parts.append(item)
        elif isinstance(value, str):
            text_parts.append(value)
    
    full_text = " ".join(text_parts)
    if not full_text.strip():
        return []
    
    categories_list = ", ".join(CATEGORIES)
    prompt = f"""Extract all housing maintenance items, infrastructure problems, and building systems mentioned in this meeting excerpt. For each item, provide:
1. The item name (e.g., "elevator", "faucet", "door")
2. The category it belongs to (choose from: {categories_list})
3. A brief note about what was said

Format your response as a JSON array with objects like:
[
  {{"name": "elevator", "category": "Big Equipment", "note": "elevator was frequently breaking down"}},
  {{"name": "faucet", "category": "Plumbing", "note": "residents discussed replacement of faucets"}}
]

Return ONLY the JSON array, no other text.

Meeting excerpt:
{full_text}"""

    try:
        result = subprocess.run(
            ["llm", "prompt", "-m", model, prompt],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"  ✗ Claude error: {result.stderr}")
            return []
        
        # Parse the JSON response
        json_str = result.stdout.strip()
        
        # Strip markdown code fence if present
        if json_str.startswith("```"):
            json_str = json_str.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:]
            json_str = json_str.strip()
        
        items = json.loads(json_str)
        return items if isinstance(items, list) else []
    
    except subprocess.TimeoutExpired:
        print(f"  ✗ Claude timeout")
        return []
    except json.JSONDecodeError as e:
        print(f"  ✗ Invalid JSON from Claude: {e}")
        return []
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return []

def normalize_category(cat: str) -> str:
    """Normalize category name."""
    cat_lower = cat.lower()
    for valid_cat in CATEGORIES:
        if cat_lower == valid_cat.lower():
            return valid_cat
    return "Other"

def safe_parse_date(date_str: str) -> datetime:
    """Try to parse date string."""
    if not date_str or date_str == "Unknown Date":
        return datetime.min
    
    formats = ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return datetime.min

def main():
    parser = argparse.ArgumentParser(description="Extract and categorize housing items from meetings using Claude.")
    parser.add_argument(
        "--model",
        default="anthropic/claude-sonnet-4-6",
        help="Claude model to use (default: anthropic/claude-sonnet-4-6)"
    )
    args = parser.parse_args()
    
    meetings_path = Path("./extracted_json/all_meetings.json")
    
    if not meetings_path.exists():
        print(f"Error: {meetings_path} not found")
        return
    
    print(f"Loading meetings...")
    meetings = load_meetings(meetings_path)
    
    # Aggregate data
    item_mentions: Dict[str, List[Dict]] = defaultdict(list)
    item_counts: Dict[str, int] = defaultdict(int)
    item_categories: Dict[str, str] = {}
    item_first_seen: Dict[str, tuple] = {}
    
    print(f"Processing {len(meetings)} meetings with Claude (model: {args.model})...")
    for i, meeting in enumerate(meetings, 1):
        print(f"  [{i}/{len(meetings)}] {meeting.get('filename', 'Unknown')}...", end=" ", flush=True)
        
        filename = meeting.get("filename", "Unknown")
        date = meeting.get("date", "Unknown Date")
        
        items = extract_items_from_meeting_with_claude(meeting, args.model)
        
        if items:
            print(f"found {len(items)} items")
            for item_data in items:
                name = (item_data.get("name") or "").strip().lower()
                if not name:
                    continue
                
                category = normalize_category(item_data.get("category", "Other"))
                note = (item_data.get("note") or "").strip()
                
                item_counts[name] += 1
                item_categories[name] = category
                
                if name not in item_first_seen:
                    item_first_seen[name] = (filename, date)
                
                item_mentions[name].append({
                    "filename": filename,
                    "date": date,
                    "snippet": note,
                })
        else:
            print("no items")
    
    # Sort mentions by date for each item
    for canonical in item_mentions:
        item_mentions[canonical].sort(
            key=lambda m: safe_parse_date(m["date"])
        )
    
    # Generate grouped output (by category)
    grouped_by_category: Dict[str, List[Dict]] = defaultdict(list)
    for canonical in sorted(item_counts.keys()):
        category = item_categories[canonical]
        first_file, first_date = item_first_seen[canonical]
        
        grouped_by_category[category].append({
            "name": canonical.title(),
            "canonical": canonical,
            "count": item_counts[canonical],
            "first_mentioned_filename": first_file,
            "first_mentioned_date": first_date,
            "example_snippet": item_mentions[canonical][0]["snippet"] if item_mentions[canonical] else "",
        })
    
    # Sort items within each category by count descending
    for category in grouped_by_category:
        grouped_by_category[category].sort(
            key=lambda x: (-x["count"], x["name"].lower())
        )
    
    # Generate per-item detailed output
    items_detail = []
    for canonical in sorted(item_counts.keys()):
        category = item_categories[canonical]
        first_file, first_date = item_first_seen[canonical]
        
        items_detail.append({
            "canonical": canonical,
            "name": canonical.title(),
            "category": category,
            "count": item_counts[canonical],
            "first_mentioned_filename": first_file,
            "first_mentioned_date": first_date,
            "mentions": item_mentions[canonical],
        })
    
    items_detail.sort(key=lambda x: (-x["count"], x["name"].lower()))
    
    # Write outputs as CSV
    output_dir = Path("./extracted_json")
    output_dir.mkdir(exist_ok=True)
    
    # Write grouped items CSV
    grouped_path = output_dir / "grouped_items.csv"
    with open(grouped_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "category",
                "name",
                "canonical",
                "count",
                "first_mentioned_filename",
                "first_mentioned_date",
                "example_snippet",
            ],
        )
        writer.writeheader()
        for category, items in sorted(grouped_by_category.items()):
            for item in items:
                writer.writerow({
                    "category": category,
                    "name": item["name"],
                    "canonical": item["canonical"],
                    "count": item["count"],
                    "first_mentioned_filename": item["first_mentioned_filename"],
                    "first_mentioned_date": item["first_mentioned_date"],
                    "example_snippet": item["example_snippet"],
                })
    print(f"\nWrote grouped items to {grouped_path}")
    
    # Write items with mentions CSV (denormalized: one row per mention)
    items_path = output_dir / "items_with_mentions.csv"
    with open(items_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "canonical",
                "name",
                "category",
                "total_count",
                "mention_filename",
                "mention_date",
                "mention_snippet",
            ],
        )
        writer.writeheader()
        for item in items_detail:
            for mention in item["mentions"]:
                writer.writerow({
                    "canonical": item["canonical"],
                    "name": item["name"],
                    "category": item["category"],
                    "total_count": item["count"],
                    "mention_filename": mention["filename"],
                    "mention_date": mention["date"],
                    "mention_snippet": mention["snippet"],
                })
    print(f"Wrote items with mentions to {items_path}")
    
    # Summary
    total_unique_items = len(item_counts)
    total_mentions = sum(item_counts.values())
    print(f"\nExtraction complete:")
    print(f"  {total_unique_items} unique items found")
    print(f"  {total_mentions} total mentions across all meetings")
    print(f"  Categories: {', '.join(sorted(set(item_categories.values())))}")

if __name__ == "__main__":
    main()
