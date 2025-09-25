import os
import re
import json
import sys
import requests
from bs4 import BeautifulSoup

PUSHOVER_TOKEN = os.environ["PUSHOVER_TOKEN"]
PUSHOVER_USER  = os.environ["PUSHOVER_USER"]

STATE_FILE     = "latest_internship.json"
RAW_URL        = "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md"
SECTION_TITLE  = "Data Science, AI & Machine Learning Internship Roles"
TIMEOUT_SEC    = 30

def send_pushover(msg: str, title: str = "New Internship Alert") -> None:
    resp = requests.post(
        "https://api.pushover.net/1/messages.json",
        data={"token": PUSHOVER_TOKEN, "user": PUSHOVER_USER, "message": msg, "title": title},
        timeout=TIMEOUT_SEC,
    )
    print("Pushover:", resp.status_code, resp.text[:200])
    resp.raise_for_status()

def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text) 
    text = re.sub(r"^[^\w\[]+\s*", "", text)             
    return " ".join(text.split())

def get_section_slice(md: str) -> str:
    lines = md.splitlines()
    try:
        sec_idx = next(
            i for i, ln in enumerate(lines)
            if ln.strip().startswith("##") and SECTION_TITLE.lower() in ln.lower()
        )
    except StopIteration:
        raise RuntimeError("Could not find the Data Science/AI section header.")

    try:
        next_header = next(i for i in range(sec_idx + 1, len(lines)) if lines[i].startswith("## "))
    except StopIteration:
        next_header = len(lines)

    return "\n".join(lines[sec_idx:next_header])

def parse_html_table(html_snippet: str):
    soup = BeautifulSoup(html_snippet, "html.parser")
    tbl = soup.find("table")
    if not tbl:
        return None

    tbody = tbl.find("tbody") or tbl
    first_row = tbody.find("tr")
    if not first_row:
        return None

    tds = first_row.find_all("td")
    if len(tds) < 3:
        return None

    company  = tds[0].get_text(" ", strip=True)
    role     = tds[1].get_text(" ", strip=True)
    location = tds[2].get_text(" ", strip=True)

    return {
        "company": strip_markdown(company),
        "role": strip_markdown(role),
        "location": strip_markdown(location),
    }

def parse_markdown_table(section_text: str):
    sec_lines = section_text.splitlines()
    start = None
    for i in range(len(sec_lines) - 1):
        if sec_lines[i].lstrip().startswith("|") and re.match(r"^\s*\|[-:\s|]+\|\s*$", sec_lines[i+1]):
            start = i
            break
    if start is None or start + 2 >= len(sec_lines):
        return None

    first_data_row = sec_lines[start + 2]

    def split_cols(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    cols = split_cols(first_data_row)
    if len(cols) < 3:
        return None

    return {
        "company": strip_markdown(cols[0]),
        "role": strip_markdown(cols[1]),
        "location": strip_markdown(cols[2]),
    }

def get_latest_internship():
    md = requests.get(RAW_URL, timeout=TIMEOUT_SEC).text
    sec_text = get_section_slice(md)

    result = parse_html_table(sec_text)
    if result:
        return result
    
    result = parse_markdown_table(sec_text)
    if result:
        return result

    raise RuntimeError("Could not find a table in the target section (HTML or Markdown).")

def main():
    try:
        latest = get_latest_internship()
        print("Latest parsed:", latest)
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        raise

    try:
        with open(STATE_FILE, "r") as f:
            prev = json.load(f)
    except FileNotFoundError:
        prev = {}

    if latest != prev:
        msg = f"🚨 New Internship!\n{latest['company']} — {latest['role']}\n📍 {latest['location']}"
        send_pushover(msg)
        with open(STATE_FILE, "w") as f:
            json.dump(latest, f)
        print("State updated. Notification sent.")
    else:
        print("No change; not sending push.")

if __name__ == "__main__":
    main()
