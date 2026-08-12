# EmailPro — AI-Powered Email Campaign Manager

A Flask app that lets you upload an email list, auto-classify contacts as
**Business** or **Individual** using the Gemini API, and send a bulk Gmail
campaign with delivery tracking — matching the "EmailPro" tutorial spec.

## Features
- **Upload** — drop in a CSV of emails, duplicates removed automatically.
- **Classify** — Gemini AI splits contacts into Business / Individual
  (falls back to a domain heuristic if no `GEMINI_API_KEY` is set, so the
  app still runs end-to-end without one).
- **Send** — compose a subject/body, pick an audience, optionally attach a
  file, and send through Gmail SMTP with a configurable delay between sends
  and automatic SMTP reconnect on drop.
- **Reports** — live delivered/failed counts, per-email delivery log, and a
  downloadable CSV report.
- **Settings** — configure sender email/app password, default subject and
  message, send delay, and automation toggles.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the app — no credentials needed to try it**
   ```bash
   python app.py
   ```
   Visit `http://127.0.0.1:5000`. **Demo Mode is on by default**, so you
   can walk through Upload → Classify → Send → Report immediately with no
   `.env` file at all. Every recipient is marked "sent (demo)" — no Gmail
   login happens and no real email is sent.

3. **When you're ready to send real emails**, go to **Settings**:
   - Turn **Demo Mode** off.
   - Add `GMAIL_EMAIL` / `GMAIL_APP_PASSWORD` (or copy `.env.example` to
     `.env` and fill them in instead). The app password comes from a
     Gmail account with 2‑Step Verification enabled, via
     **Google Account → Security → App Passwords**.
   - `GEMINI_API_KEY` is optional. Get one from Google AI Studio. Without
     it, classification uses a free-mail-domain heuristic instead
     (gmail.com/yahoo.com/etc. → Individual, everything else → Business).

## Project structure
```
EmailPro/
├── app.py              # Flask routes: /, /upload, /classify, /send, /report, /settings
├── config.py            # Env-based configuration
├── utilis.py             # CSV helpers (dedupe, read/write, file size)
├── emailClassifier.py   # Gemini-based BUSINESS/INDIVIDUAL classifier
├── templates/            # index, upload, classify, send_mail, report, settings, base
├── static/css/style.css # Dashboard styling
├── uploads/              # Runtime CSVs: Email.csv, BusinessEmails.csv, ...
├── assets/               # Optional default attachment
├── requirements.txt
└── .env.example
```

## How a campaign flows
1. Upload `Email.csv` → duplicates stripped.
2. Run classification → writes `BusinessEmails.csv` / `IndividualsEmails.csv`.
3. Compose a campaign, pick an audience, optionally attach a file.
4. App logs in to Gmail SMTP (SSL, port 465), sends one message per
   recipient with a delay between sends, reconnecting automatically if the
   session drops.
5. Every send (success/failure) is appended to `uploads/sent_log.csv` and
   summarized on the Reports page, with a CSV export.

## Notes on security
- Credentials live only in `.env` / `uploads/settings.json` — never
  hard-coded in source.
- `.env` should be added to `.gitignore` before pushing this to a repo.
