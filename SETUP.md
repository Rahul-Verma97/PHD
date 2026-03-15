# PhD Professor Hiring Monitor — Setup Guide

Monitors 100 professors across 20 universities and alerts you instantly
when any of them post that they're accepting PhD students.

---

## Quick Start (5 steps)

### Step 1 — Clone & install locally

```bash
cd phd-monitor
pip install -r requirements.txt
playwright install chromium
```

### Step 2 — Set up Telegram Bot (recommended, free)

1. Open Telegram → message **@BotFather** → type `/newbot`
2. Follow prompts → copy the **bot token**
3. Start a chat with your new bot (click the link BotFather gives you)
4. Visit this URL in your browser (replace TOKEN):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
5. Send any message to your bot, refresh the URL, find `"id"` under `"chat"` — that's your **chat_id**

### Step 3 — Configure secrets

```bash
cp .env.example .env
# Edit .env with your Telegram token, chat_id, and optionally Gmail
```

### Step 4 — Test locally

```bash
# Dry run — no alerts sent, just logs
DRY_RUN=true python main.py

# Real run on just 5 professors
MAX_PROFESSORS_PER_RUN=5 python main.py
```

### Step 5 — Deploy to GitHub Actions (free, runs daily)

1. Push this repo to GitHub (can be private)
2. Go to **Settings → Secrets and variables → Actions**
3. Add these secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GMAIL_ADDRESS` (optional)
   - `GMAIL_APP_PASSWORD` (optional)
   - `OPENAI_API_KEY` (optional)
4. Go to **Actions** tab → enable workflows
5. Click **Run workflow** to test manually first

The monitor will now run automatically every day at **6:00 AM UTC (11:30 AM IST)**.

---

## Adding Google Alerts (Highly Recommended)

For each professor, set up a Google Alert:

1. Go to [google.com/alerts](https://google.com/alerts)
2. Search: `"Graham Neubig" phd students hiring`
3. Click **Show options** → Deliver to: **RSS feed**
4. Copy the RSS URL and paste it into `professors.yaml` under `google_alert_rss`

This catches news articles and blog posts that website scraping might miss.

---

## Adding / Updating Professors

Edit `config/professors.yaml`. Each professor entry looks like:

```yaml
- id: cmu_001
  name: "Professor Name"
  university: "University Name"
  department: "Department"
  research_area: "Research focus"
  website: "https://prof.homepage.edu"
  lab_page: "https://lab.homepage.edu"
  twitter_handle: "twitterhandle"    # without @
  google_alert_rss: ""               # paste Google Alert RSS URL here
  priority: high                     # high / medium / low
```

---

## Tuning Alert Sensitivity

Edit `config/keywords.yaml`:
- Add phrases to `strong_signals` to catch more announcements
- Add phrases to `negative_filters` to reduce false positives
- Lower `weak_signals` threshold in `core/classifier.py` (default: 2 matches)

---

## File Structure

```
phd-monitor/
├── config/
│   ├── professors.yaml    ← 100 professors across 20 universities
│   └── keywords.yaml      ← hiring signal keywords
├── core/
│   ├── classifier.py      ← keyword + optional LLM classification
│   ├── state_manager.py   ← SQLite deduplication
│   └── alert_engine.py    ← Telegram + Email alerts
├── scrapers/
│   ├── website_scraper.py ← professor homepages + lab pages
│   ├── twitter_scraper.py ← Twitter/X via Nitter RSS
│   └── rss_scraper.py     ← lab RSS feeds + Google Alerts
├── data/
│   ├── state.db           ← SQLite (auto-created, git-ignored)
│   └── alerts_log.json    ← human-readable log of all alerts
├── .github/workflows/
│   └── monitor.yml        ← GitHub Actions daily schedule
├── main.py                ← entry point
└── requirements.txt
```

---

## Cost

| Component | Cost |
|---|---|
| GitHub Actions | Free (< 50 min/month) |
| Telegram alerts | Free |
| Gmail alerts | Free |
| OpenAI LLM verification | ~$0.10–0.50/month (optional) |
| **Total** | **$0 – $0.50/month** |
