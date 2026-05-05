import json
import subprocess
import time
import re
import ast
from pathlib import Path
from collections import defaultdict

ALL_FILE = Path("./extracted_json/all_meetings.json")
OUT_DIR = Path("./extracted_json")
OUT_DIR.mkdir(exist_ok=True)

DEFAULT_MODEL = "groq/llama-3.1-8b-instant"

# Keyword fallback and category map.
# This is the second pass that catches specific fixtures the LLM may skip.
KEYWORD_RULES = [
    # big equipment / building systems
    ("elevator", "elevator", "big_equipment"),
    ("lift", "lift", "big_equipment"),
    ("boiler", "boiler", "big_equipment"),
    ("heater", "heater", "big_equipment"),
    ("furnace", "furnace", "big_equipment"),
    ("hvac", "hvac", "hvac"),
    ("air conditioner", "air conditioner", "hvac"),
    ("ac unit", "air conditioner", "hvac"),
    ("air conditioning", "air conditioning", "hvac"),
    ("ventilation", "ventilation", "hvac"),
    ("vent", "vent", "hvac"),
    ("radiator", "radiator", "hvac"),
    # plumbing fixtures
    ("faucet", "faucet", "plumbing_fixtures"),
    ("sink", "sink", "plumbing_fixtures"),
    ("toilet", "toilet", "plumbing_fixtures"),
    ("tub", "tub", "plumbing_fixtures"),
    ("bathtub", "bathtub", "plumbing_fixtures"),
    ("shower", "shower", "plumbing_fixtures"),
    ("drain", "drain", "plumbing_fixtures"),
    ("pipe", "pipe", "plumbing_fixtures"),
    ("plumbing", "plumbing", "plumbing_fixtures"),
    # accessibility / safety features
    ("grab bar", "grab bar", "accessibility_safety"),
    ("handicap handle", "handicap handle", "accessibility_safety"),
    ("handrail", "handrail", "accessibility_safety"),
    ("rail", "rail", "accessibility_safety"),
    ("walker", "walker", "accessibility_safety"),
    ("wheelchair", "wheelchair", "accessibility_safety"),
    ("smoke detector", "smoke detector", "accessibility_safety"),
    ("carbon monoxide detector", "carbon monoxide detector", "accessibility_safety"),
    # electrical
    ("electrical", "electrical", "electrical"),
    ("outlet", "outlet", "electrical"),
    ("socket", "socket", "electrical"),
    ("switch", "switch", "electrical"),
    ("breaker", "breaker", "electrical"),
    ("wiring", "wiring", "electrical"),
    ("light", "light", "electrical"),
    ("lighting", "lighting", "electrical"),
    # doors / windows
    ("door", "door", "doors_windows"),
    ("window", "window", "doors_windows"),
    ("lock", "lock", "doors_windows"),
    ("hinge", "hinge", "doors_windows"),
    ("screen", "screen", "doors_windows"),
    # appliances
    ("stove", "stove", "appliances"),
    ("oven", "oven", "appliances"),
    ("refrigerator", "refrigerator", "appliances"),
    ("fridge", "fridge", "appliances"),
    ("microwave", "microwave", "appliances"),
    ("dishwasher", "dishwasher", "appliances"),
    ("washing machine", "washing machine", "appliances"),
    ("washer", "washer", "appliances"),
    ("dryer", "dryer", "appliances"),
    # services / maintenance issues
    ("roof", "roof", "services"),
    ("plumb", "plumbing", "services"),
    ("water", "water", "services"),
    ("sewer", "sewer", "services"),
    ("garbage", "garbage", "services"),
    ("trash", "trash", "services"),
]

CATEGORY_NAMES = {
    "big_equipment": "Big Equipment",
    "small_equipment": "Small Equipment",
    "plumbing_fixtures": "Plumbing Fixtures",
    "accessibility_safety": "Accessibility / Safety Features",
    "hvac": "HVAC",
    "electrical": "Electrical",
    "doors_windows": "Doors / Windows",
    "appliances": "Appliances",
    "services": "Services",
    "other": "Other",
}

CATEGORY_ORDER = {
    "big_equipment": 0,
    "small_equipment": 1,
    "plumbing_fixtures": 2,
    "accessibility_safety": 3,
    "hvac": 4,
    "electrical": 5,
    "doors_windows": 6,
    "appliances": 7,
    "services": 8,
    "other": 9,
}

PROMPT_TEMPLATE = '''Extract housing-related items, maintenance issues, equipment, fixtures, and accessibility features from the meeting text.
Be strict and specific: capture every item or fixture mentioned individually.
Do NOT collapse specific objects into broader categories.
For example, keep "faucet", "sink", "toilet", "grab bar", "handicap handle", "vent", and "radiator" as separate items when they appear.
If a sentence mentions several items, return each item separately.

Return ONLY a JSON array of objects with fields:
- name: short item name (string)
- category: one of ["big_equipment","small_equipment","plumbing_fixtures","accessibility_safety","hvac","electrical","doors_windows","appliances","services","other"]
- notes: short textual note or quote showing the mention

Text:
"""{text}"""

Do not return any extra text or explanation.'''


def call_llm(text, model=DEFAULT_MODEL, timeout=60):
    prompt = PROMPT_TEMPLATE.format(text=text)
    try:
        # prefer deterministic output (note: some llm CLI builds don't support --temperature)
        llm_cmd = ["llm", "prompt", "-m", model, prompt]
        proc = subprocess.run(llm_cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            print("LLM error:", proc.stderr.strip())
            return None
        out = proc.stdout.strip()
        # strip markdown fences if present
        if out.startswith("```"):
            parts = out.split("```")
            if len(parts) >= 2:
                out = parts[1]
                if out.startswith("json"):
                    out = out[4:]
                out = out.strip()
        # Try several strategies to recover a JSON blob
        def try_parse(s):
            s = s.strip()
            try:
                return json.loads(s)
            except Exception:
                pass
            # try to extract a JSON object/array within the text
            m = re.search(r'(\{.*\}|\[.*\])', s, re.S)
            if m:
                blob = m.group(1)
                try:
                    return json.loads(blob)
                except Exception:
                    try:
                        # try single->double quotes
                        return json.loads(blob.replace("'", '"'))
                    except Exception:
                        pass
                    try:
                        return ast.literal_eval(blob)
                    except Exception:
                        pass
            # final attempt: replace single quotes globally
            try:
                return json.loads(s.replace("'", '"'))
            except Exception:
                pass
            return None

        data = try_parse(out)

        if data is None:
            # retry once with a clarifying prompt
            retry_prompt = "Your previous response was not valid JSON. Return ONLY a valid JSON array/object that matches the specification, with no surrounding text or code fences."
            try:
                # combine retry clarification and the original prompt into one prompt string
                prompt_text = retry_prompt + "\n\n" + prompt
                proc2 = subprocess.run(["llm", "prompt", "-m", model, prompt_text], capture_output=True, text=True, timeout=timeout)
                out2 = proc2.stdout.strip() if proc2.returncode == 0 else ""
                if out2.startswith("```"):
                    parts = out2.split("```")
                    if len(parts) >= 2:
                        out2 = parts[1]
                        if out2.startswith("json"):
                            out2 = out2[4:]
                        out2 = out2.strip()
                data = try_parse(out2)
                if data is None:
                    print("Invalid JSON from LLM (falling back to keywords)")
                    return None
                return data
            except subprocess.TimeoutExpired:
                print("LLM retry timeout")
                return None
        return data
    except subprocess.TimeoutExpired:
        print("LLM timeout")
        return None


def keyword_extract(text):
    found = []
    lower = text.lower()
    for kw, name, cat in KEYWORD_RULES:
        if kw in lower:
            # capture a short snippet around the first hit
            idx = lower.find(kw)
            snippet = text[max(0, idx-40): idx+len(kw)+40].replace('\n',' ')
            found.append({"name": name, "category": cat, "notes": snippet})
    return found


def merge_items(primary_items, secondary_items):
    merged = {}

    for it in list(primary_items or []) + list(secondary_items or []):
        if not isinstance(it, dict):
            continue
        name = normalize_name(str(it.get("name", "unknown")))
        cat = str(it.get("category") or "other").strip().lower()
        notes = str(it.get("notes", "")).strip()
        key = f"{name}|{cat}"
        if key not in merged:
            merged[key] = {"name": name, "category": cat, "notes": notes}
        elif notes and notes not in merged[key]["notes"]:
            merged[key]["notes"] = (merged[key]["notes"] + " | " + notes).strip(" |")

    return list(merged.values())


def pretty_category(cat):
    return CATEGORY_NAMES.get(cat, cat.replace("_", " ").title())


def normalize_name(name):
    return name.strip().lower()


def aggregate_items(meetings, model=DEFAULT_MODEL):
    all_items = {}
    items_by_meeting = []

    for m in meetings:
        filename = m.get("filename")
        date = m.get("date")
        text_parts = []
        for k in ["residents_comments", "executive_directors_report", "raw_text"]:
            v = m.get(k)
            if isinstance(v, list):
                text_parts.append("\n".join(v))
            elif isinstance(v, str):
                text_parts.append(v)
        text = "\n\n".join([p for p in text_parts if p])

        items = call_llm(text, model=model) or []
        keyword_items = keyword_extract(text)
        items = merge_items(items, keyword_items)

        meeting_items = []
        for it in items:
            name = normalize_name(it.get("name","unknown"))
            cat = str(it.get("category") or "other").strip().lower()
            notes = it.get("notes","")

            meeting_items.append({"name": name, "category": cat, "notes": notes})

            key = name
            if key not in all_items:
                all_items[key] = {"name": name, "category": cat, "count": 0, "mentions": []}
            all_items[key]["count"] += 1
            all_items[key]["mentions"].append({"filename": filename, "date": date, "notes": notes})

        items_by_meeting.append({"filename": filename, "date": date, "items": meeting_items})
        # be polite with rate limits
        time.sleep(0.5)

    return all_items, items_by_meeting


def main(model=DEFAULT_MODEL):
    if not ALL_FILE.exists():
        print(f"Missing {ALL_FILE}. Run merge_json.py first.")
        return

    meetings = json.loads(ALL_FILE.read_text(encoding="utf-8"))
    all_items, items_by_meeting = aggregate_items(meetings, model=model)

    OUT_DIR.joinpath("items_by_meeting.json").write_text(json.dumps(items_by_meeting, indent=2), encoding="utf-8")
    OUT_DIR.joinpath("all_items_summary.json").write_text(json.dumps(list(all_items.values()), indent=2), encoding="utf-8")

    # CSV exports
    try:
        import csv

        # 1) Existing flat summary, kept for compatibility.
        with open(OUT_DIR / "all_items_summary.csv", "w", newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(["name","category","count","first_mentioned_in","example_note"])
            for v in sorted(all_items.values(), key=lambda x: -x["count"]):
                first = v["mentions"][0]["filename"] if v["mentions"] else ""
                note = (v["mentions"][0]["notes"][:120]) if v["mentions"] else ""
                writer.writerow([v["name"], v["category"], v["count"], first, note])

        # 2) Grouped table: rows sorted by category so spreadsheet users can read it like sections.
        grouped_rows = sorted(
            all_items.values(),
            key=lambda x: (CATEGORY_ORDER.get(x["category"], 99), x["name"])
        )
        with open(OUT_DIR / "all_items_grouped.csv", "w", newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(["category_group", "name", "count", "first_mentioned_in", "example_note"])
            for v in grouped_rows:
                first = v["mentions"][0]["filename"] if v["mentions"] else ""
                note = (v["mentions"][0]["notes"][:120]) if v["mentions"] else ""
                writer.writerow([pretty_category(v["category"]), v["name"], v["count"], first, note])
    except Exception:
        pass

    print(f"Wrote {len(items_by_meeting)} per-meeting files and {len(all_items)} unique items.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--model', default=DEFAULT_MODEL)
    args = p.parse_args()
    main(model=args.model)
