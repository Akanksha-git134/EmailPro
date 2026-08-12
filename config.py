"""
config.py
Central configuration for EmailPro.

All secrets are loaded from environment variables (.env file) — never
hard-code credentials in source files.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Gmail / SMTP credentials ---
EMAIL = os.getenv("GMAIL_EMAIL", "")
APP_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
MONITOR_EMAIL = os.getenv("MONITOR_EMAIL", EMAIL)  # CC'd on every send for visibility

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # SSL

# --- Gemini API (AI classification) ---
secret_key = os.getenv("GEMINI_API_KEY", "")

# --- Run configuration ---
DEFAULT_SUBJECT = os.getenv("DEFAULT_SUBJECT", "Singing Bowl Product Presentation")
DEFAULT_MESSAGE = os.getenv(
    "DEFAULT_MESSAGE",
    "Hello,\n\nWe would like to introduce our Singing Bowl products.\n\nThank you.",
)
EMAIL_DELAY_SECONDS = int(os.getenv("EMAIL_DELAY_SECONDS", "5"))
DAILY_SEND_LIMIT = int(os.getenv("DAILY_SEND_LIMIT", "100"))

# --- File paths ---
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
PRESENTATION_PATH = os.getenv("PRESENTATION_PATH", "assets/company_presentation.pdf")

EMAIL_CSV = os.path.join(UPLOAD_FOLDER, "Email.csv")
BUSINESS_CSV = os.path.join(UPLOAD_FOLDER, "BusinessEmails.csv")
INDIVIDUAL_CSV = os.path.join(UPLOAD_FOLDER, "IndividualsEmails.csv")
SENT_LOG_CSV = os.path.join(UPLOAD_FOLDER, "sent_log.csv")
SETTINGS_JSON = os.path.join(UPLOAD_FOLDER, "settings.json")

ALLOWED_ATTACHMENT_EXT = {"pdf", "ppt", "pptx", "doc", "docx"}
