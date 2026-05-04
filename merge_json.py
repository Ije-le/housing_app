from pathlib import Path
import json

OUTPUT_DIR = Path("./extracted_json")
OUT_FILE = OUTPUT_DIR / "all_meetings.json"

OUTPUT_DIR.mkdir(exist_ok=True)

files = sorted([p for p in OUTPUT_DIR.glob("*.json") if p.name != OUT_FILE.name])
meetings = []

for f in files:
    try:
        txt = f.read_text(encoding="utf-8")
        obj = json.loads(txt)
        meetings.append(obj)
    except Exception as e:
        print(f"Skipping {f.name}: {e}")

OUT_FILE.write_text(json.dumps(meetings, indent=2), encoding="utf-8")
print(f"Wrote {len(meetings)} meetings to {OUT_FILE}")
