import os
import json
import re
import sys
import subprocess
from pdf2image import convert_from_path
import pytesseract
from pathlib import Path
from datetime import datetime
import click

PDF_DIR = "./pdfs/housing_authority"
OUTPUT_DIR = "./extracted_json"
ALL_MEETINGS_FILE = Path(OUTPUT_DIR) / "all_meetings.json"

Path(OUTPUT_DIR).mkdir(exist_ok=True)

# Default model to use for parsing
DEFAULT_MODEL = "groq/llama-3.1-8b-instant"

def extract_date(text):
    """Try to extract a date from the text."""
    # Look for common date patterns
    patterns = [
        r'(\w+\s+\d{1,2},?\s+\d{4})',  # June 21, 2021 or June 21 2021
        r'(\d{1,2}/\d{1,2}/\d{4})',     # 06/21/2021
        r'(\d{1,2}-\d{1,2}-\d{4})',     # 06-21-2021
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return "Unknown Date"

def extract_section(text, *headers):
    """Extract text from a section with any of the given headers (case-insensitive)."""
    lower_text = text.lower()
    headers_lower = [h.lower() for h in headers]
    
    # Find the position of any matching header
    start_pos = -1
    for header in headers_lower:
        pos = lower_text.find(header)
        if pos != -1:
            start_pos = pos
            break
    
    if start_pos == -1:
        return []
    
    # Find the next header (or end of text)
    next_header_pos = len(text)
    for header in headers_lower:
        pos = lower_text.find(header, start_pos + len(headers[0]))
        if pos != -1 and pos < next_header_pos:
            next_header_pos = pos
    
    section_text = text[start_pos:next_header_pos]
    
    # Split by lines and clean up
    lines = section_text.split('\n')
    content = []
    
    for line in lines[1:]:  # Skip the header line
        line = line.strip()
        if line and len(line) > 5:  # Filter out very short lines
            content.append(line)
    
    return content[:10]  # Return up to 10 items

def extract_attendees(text):
    """Extract attendees from common patterns like 'Name: Title'."""
    attendees = []
    
    # Look for lines with colons (common format for attendee lists)
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        # Match patterns like "Chairperson: Ricardo Banks" or "Present: Name"
        if ':' in line and any(role in line.lower() for role in ['chairperson', 'president', 'vice', 'secretary', 'treasurer', 'present', 'board']):
            attendees.append(line)
    
    return attendees[:15]  # Return up to 15 attendees

def extract_decisions(text):
    """Extract decisions from the document."""
    decisions = []
    
    lower_text = text.lower()
    
    # Look for decision-related keywords
    if "decision" in lower_text or "approved" in lower_text or "resolved" in lower_text:
        lines = text.split('\n')
        capture = False
        
        for line in lines:
            line_lower = line.lower().strip()
            if "decision" in line_lower:
                capture = True
                continue
            
            if capture and line.strip():
                if len(line.strip()) > 10:
                    decisions.append(line.strip())
                    if len(decisions) >= 10:  # Stop after 10 decisions
                        break
            
            if capture and not line.strip():
                if len(decisions) > 0:
                    break
    
    return decisions

def parse_pdf_to_json(pdf_path, model=DEFAULT_MODEL):
    """Extract text from PDF via OCR, then use LLM to parse into structured JSON."""
    print(f"Processing {pdf_path.name}...")
    
    try:
        # Extract text from PDF via OCR
        pages = convert_from_path(pdf_path, dpi=300)
        full_text = ""
        
        for i, page in enumerate(pages):
            page_text = pytesseract.image_to_string(page)
            full_text += f"\n--- PAGE {i+1} ---\n{page_text}"
        
        # Use LLM to parse the text into structured JSON
        prompt = f"""Extract meeting minutes information from the following text and return ONLY a valid JSON object with these exact fields:
- filename: the PDF filename
- date: the meeting date (extract date if mentioned, or "Unknown Date")
- attendees: list of attendee names/titles
- residents_comments: list of resident comments (handle both "residents comments" and "comments-tenant and general public" sections)
- executive_directors_report: list of points from executive director report (or "chief executive officers report")
- decisions: list of decisions made
- raw_text: the original text

Return ONLY the JSON object, no other text.

Text:
{full_text}"""
        
        # Call llm with the model
        try:
            result = subprocess.run(
                ["llm", "prompt", "-m", model, prompt],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"  ✗ LLM error: {result.stderr}")
                return None
            
            # Parse the JSON response
            json_str = result.stdout.strip()
            
            # Strip markdown code fence if present
            if json_str.startswith("```"):
                json_str = json_str.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]  # Remove 'json' language marker
                json_str = json_str.strip()
            
            data = json.loads(json_str)
            data["filename"] = pdf_path.name
            
            return data
        
        except subprocess.TimeoutExpired:
            print(f"  ✗ LLM timeout on {pdf_path.name}")
            return None
        except json.JSONDecodeError as e:
            print(f"  ✗ Invalid JSON from LLM on {pdf_path.name}: {e}")
            print(f"     Response was: {result.stdout[:200]}")
            return None
    
    except Exception as e:
        print(f"  ✗ ERROR on {pdf_path.name}: {e}")
        return None

pdf_files = list(Path(PDF_DIR).glob("*.pdf"))
print(f"Found {len(pdf_files)} PDFs\n")

@click.command()
@click.option('--model', default=DEFAULT_MODEL, help=f'Groq model to use (default: {DEFAULT_MODEL})')
def main(model):
    """Extract meeting minutes from PDFs using OCR + LLM parsing."""
    print(f"Using model: {model}\n")

    all_meetings = []
    
    for pdf_path in sorted(pdf_files):
        result = parse_pdf_to_json(pdf_path, model=model)
        
        if result:
            all_meetings.append(result)

    ALL_MEETINGS_FILE.write_text(json.dumps(all_meetings, indent=2), encoding="utf-8")
    print(f"Wrote {len(all_meetings)} meetings to {ALL_MEETINGS_FILE.name}")
    
    print("\nDone.")

if __name__ == "__main__":
    main()