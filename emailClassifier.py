"""
emailClassifier.py
Classifies email addresses into BUSINESS or INDIVIDUAL using the
Gemini API. Falls back to a simple heuristic if no API key is
configured, so the app remains usable without a Gemini key.
"""

import json
import re

from config import secret_key

API_KEY = secret_key

_client = None
if API_KEY:
    try:
        from google import genai

        _client = genai.Client(api_key=API_KEY)
    except Exception:
        _client = None


def chunk_list(lst, size):
    """Split list into chunks of at most `size` items."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


FREE_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "icloud.com",
    "aol.com",
    "protonmail.com",
    "rediffmail.com",
}


def _heuristic_classify(emails):
    """Free-mail domains are treated as individuals; everything else
    (custom/company domains) is treated as business. Used only when
    no Gemini API key is configured."""
    result = {}
    for email in emails:
        domain = email.split("@")[-1].lower().strip()
        result[email] = "INDIVIDUAL" if domain in FREE_DOMAINS else "BUSINESS"
    return result


def classify_email_batch(emails):
    """
    Classify up to 100 emails in a single Gemini request.
    Returns dictionary:
    {
        "email@example.com": "BUSINESS",
        ...
    }
    """
    if not emails:
        return {}

    if _client is None:
        return _heuristic_classify(emails)

    prompt = f"""
You are an email classifier.

Classify each email address as either:
BUSINESS
INDIVIDUAL

A BUSINESS email uses a company/organization's own domain (not a
generic free provider). An INDIVIDUAL email uses a generic personal
provider (gmail.com, yahoo.com, hotmail.com, outlook.com, etc.).

Return ONLY a JSON object mapping each email to its label, e.g.:
{{"someone@example.com": "BUSINESS"}}

Emails to classify:
{json.dumps(emails)}
"""

    try:
        response = _client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()
        # Strip markdown code fences if present
        text = re.sub(r"^```json|```$", "", text, flags=re.MULTILINE).strip()
        parsed = json.loads(text)
        # Normalize labels and fill any missing emails with heuristic fallback
        result = {}
        for email in emails:
            label = str(parsed.get(email, "")).upper()
            if label not in ("BUSINESS", "INDIVIDUAL"):
                label = _heuristic_classify([email])[email]
            result[email] = label
        return result
    except Exception:
        return _heuristic_classify(emails)


def classify_emails(emails, batch_size=100):
    """Deduplicate + classify a full list of emails in batches."""
    unique = list(dict.fromkeys(e.strip() for e in emails if e.strip()))
    business, individual = [], []

    for batch in chunk_list(unique, batch_size):
        labels = classify_email_batch(batch)
        for email in batch:
            if labels.get(email) == "BUSINESS":
                business.append(email)
            else:
                individual.append(email)

    return business, individual
