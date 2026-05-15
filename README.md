# Housing Minutes Intelligence

This repository now includes a rebuilt Flask app for exploring five years of meeting minutes from a senior housing council. The app turns the extracted records into a public-facing newsroom-style database that surfaces recurring complaints, meeting timelines, and documented co-occurrence between issues.

## What it shows

- Searchable complaint and issue pages
- Issue families such as elevators, HVAC, plumbing, laundry, security, lighting, appliances, and accessibility
- Meeting detail pages with residents' comments, staff reports, and decisions
- Timeline and co-occurrence views that show documented patterns without claiming causation

## Run locally

```bash
python main.py
```

Then open http://127.0.0.1:5000/ in your browser.

## Data sources

- `extracted_json/all_items_grouped.csv`
- `extracted_json/cleaned_all_items_summary.json`
- `extracted_json/all_meetings.json`
- `extracted_json/items_by_meeting.json`

## Notes

The original scaffold is still present in the repository, but the rebuilt app lives in `newsapp.py` and is launched through `main.py`.
