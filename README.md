# Tax Intelligence System — Complete Setup Guide

## Overview

A fully automated system that scrapes, analyzes, and distributes Indian Income Tax updates:
- **Notifications** from incometaxindia.gov.in
- **Circulars** from incometaxindia.gov.in
- **ITAT Case Laws** from itatonline.org

Every 2 hours it runs automatically via GitHub Actions, sends Telegram alerts, and logs everything to Google Sheets.

---

## Architecture

```
main.py (Orchestrator)
├── src/scrapers.py          — Scrape listing pages
├── src/content_extractor.py — Extract clean text from HTML/PDF
├── src/section_analyzer.py  — Detect IT Act sections via regex
├── src/telegram_sender.py   — Send to Telegram channels
├── src/sheets_writer.py     — Write to Google Sheets
├── src/state_manager.py     — SQLite + JSON deduplication
├── src/logger.py            — Structured logging
└── config/settings.py       — All configuration
```

---

## Step-by-Step Setup

### Step 1: Fork / Clone this repository

```bash
git clone https://github.com/YOUR_USERNAME/tax-intel.git
cd tax-intel
```

### Step 2: Create Telegram Bot & Channels

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → follow instructions → copy the **Bot Token**
3. Create 4 channels:
   - `@YourTaxNotifications`
   - `@YourTaxCirculars`
   - `@YourTaxCaseLaws`
   - `@YourTaxImportant` *(for 80C, 148, 194J etc.)*
4. **Add your bot as Admin** to each channel
5. Get channel IDs: Either use `@username` format OR send a message to the channel and visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`

### Step 3: Set up Google Sheets

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g. "TaxIntel")
3. Enable these APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Go to **IAM & Admin → Service Accounts** → Create service account
5. Download the JSON key file
6. Create a new Google Sheet → copy its ID from the URL:
   `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`
7. **Share the Google Sheet** with the service account email (from the JSON file) as **Editor**

### Step 4: Configure GitHub Secrets

In your GitHub repository → **Settings → Secrets and Variables → Actions → New repository secret**:

| Secret Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHANNEL_NOTIF` | e.g. `@YourTaxNotifications` or `-100123456789` |
| `TELEGRAM_CHANNEL_CIRCULAR` | e.g. `@YourTaxCirculars` |
| `TELEGRAM_CHANNEL_CASELAW` | e.g. `@YourTaxCaseLaws` |
| `TELEGRAM_CHANNEL_IMPORTANT` | e.g. `@YourTaxImportant` |
| `GOOGLE_SHEETS_CREDENTIALS` | **Full contents** of the service account JSON file |
| `GOOGLE_SHEET_ID` | The Sheet ID from the URL |

### Step 5: Push to GitHub & Enable Actions

```bash
git add .
git commit -m "Initial setup"
git push origin main
```

Go to **Actions tab** → Enable workflows if prompted.

### Step 6: Test Manual Run

Go to **Actions → Tax Intelligence System → Run workflow** → Click **Run workflow**

Watch the logs. First run may take 3–5 minutes.

---

## Telegram Message Format

```
📋 Notification 🔥 IMPORTANT SECTIONS
━━━━━━━━━━━━━━━━━━
📅 Date: 2024-03-15
📌 Title: Notification No. 23/2024 regarding section 194J
🏷️ Sections: §194J, §194C
━━━━━━━━━━━━━━━━━━
📝 Summary:
The CBDT has issued notification clarifying TDS obligations under
section 194J for professional services rendered digitally...
━━━━━━━━━━━━━━━━━━
🔗 View Source
```

---

## Google Sheet Structure

Three tabs auto-created: **Notifications**, **Circulars**, **Case Laws**

| Date | Heading | Summary | Sections | Link | Source Type | Unique ID | Scraped Timestamp |
|------|---------|---------|----------|------|-------------|-----------|-------------------|

---

## Customizing Important Sections

Edit `config/settings.py`:

```python
IMPORTANT_SECTIONS = [
    "80C", "148", "194J", "271AAC",
    # Add any sections you care about
]
```

Items with these sections get sent to `TELEGRAM_CHANNEL_IMPORTANT` as well.

---

## Deduplication Design

- **SQLite DB** (`state/seen_items.db`) — primary store, fast lookups
- **JSON backup** (`state/seen_items.json`) — committed to git, survives CI resets
- On each CI run, if SQLite is empty, it restores from JSON backup
- GitHub Actions `cache` step also persists SQLite between runs

---

## Scheduling

The system runs every 2 hours via GitHub Actions cron:
```yaml
schedule:
  - cron: "0 */2 * * *"
```

GitHub Actions free tier allows ~2,000 minutes/month. This system uses ~5 min/run × 12 runs/day = 60 min/day. Well within limits.

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHANNEL_NOTIF="@your_channel"
# ... etc

# Run
python main.py
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Source URL unreachable | Tries fallback URLs, logs error, continues |
| PDF extraction fails | Falls back to PyPDF2, then title-only |
| Telegram send fails | Retries 3x with delay, logs failure |
| Sheets write fails | Retries 3x, falls back to row-by-row |
| Item causes crash | Marked seen to prevent infinite retry, logged |
| Complete run failure | Telegram error alert sent to IMPORTANT channel |

---

## Troubleshooting

**"Zero items scraped"** — The source website HTML structure may have changed. Check the logs and inspect the source page. The scrapers have 2 fallback strategies each.

**"Telegram send failed"** — Verify bot is admin in the channel and the channel ID/username is correct.

**"Google Sheets write failed"** — Check that the service account email has Editor access to the sheet.

**"Duplicate items"** — Should not happen. If it does, check that `state/seen_items.json` is being committed back to the repo by GitHub Actions.

---

## Technology Decision Notes

This system uses **Python + GitHub Actions** rather than no-code tools (Make, Zapier, n8n) because:

- **incometaxindia.gov.in** requires custom scraping logic — no RSS feed available
- **PDF extraction** requires pdfplumber/PyPDF2 — not available in no-code tools  
- **IT Section detection** requires regex over full extracted content
- **GitHub Actions** is free, reliable, has persistent state via cache+git, and handles secrets natively
- Total maintenance cost: near zero after initial setup
