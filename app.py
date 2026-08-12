from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    jsonify,
)

import json
import os
import smtplib
import time
import io
import csv

from email.message import EmailMessage

from config import (
    EMAIL,
    APP_PASS,
    MONITOR_EMAIL,
    SMTP_HOST,
    SMTP_PORT,
    secret_key,
    DEFAULT_SUBJECT,
    DEFAULT_MESSAGE,
    EMAIL_DELAY_SECONDS,
    DAILY_SEND_LIMIT,
    UPLOAD_FOLDER,
    EMAIL_CSV,
    BUSINESS_CSV,
    INDIVIDUAL_CSV,
    SENT_LOG_CSV,
    SETTINGS_JSON,
    ALLOWED_ATTACHMENT_EXT,
)
from utilis import (
    unique_emails,
    read_and_validate,
    write_emails,
    append_row,
    read_column,
    file_size_kb,
    csv_safe,
)
from emailClassifier import classify_emails

# --------------------------------------------------------------
# APP CONFIG
# --------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "emailpro_secret_key"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs("assets", exist_ok=True)

# --------------------------------------------------------------
# GLOBAL REPORT DATA
# --------------------------------------------------------------
report_data = {
    "total_emails": 0,
    "success_count": 0,
    "failed_count": 0,
    "successful_emails": [],
    "failed_emails": [],
}

# --------------------------------------------------------------
# SETTINGS HELPERS
# --------------------------------------------------------------
DEFAULT_SETTINGS = {
    "email": EMAIL,
    "app_password": APP_PASS,
    "default_subject": DEFAULT_SUBJECT,
    "default_message": DEFAULT_MESSAGE,
    "delay": EMAIL_DELAY_SECONDS,
    "auto_classify": True,
    "remove_duplicates": True,
    "skip_previously_sent": True,
    "demo_mode": False,
}


def load_settings():
    if os.path.exists(SETTINGS_JSON):
        try:
            with open(SETTINGS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = DEFAULT_SETTINGS.copy()
            merged.update(data)
            return merged
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(data):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ================================================================
# HOME
# ================================================================
@app.route("/")
def home():
    return render_template("index.html")


# ================================================================
# UPLOAD PAGE
# ================================================================
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("csv_file")

        if not file or file.filename == "":
            flash("Please select a CSV file.", "danger")
            return redirect(url_for("upload"))

        if not file.filename.lower().endswith(".csv"):
            flash("Only .csv files are supported.", "danger")
            return redirect(url_for("upload"))

        upload_path = os.path.join(app.config["UPLOAD_FOLDER"], "Email.csv")
        file.save(upload_path)

        # Validate + de-duplicate. Malformed rows are reported, not
        # silently dropped, so the operator knows the upload wasn't
        # perfectly clean rather than assuming every row made it in.
        valid, invalid = read_and_validate(upload_path)
        write_emails(upload_path, valid)

        if not valid:
            flash(
                "No valid email addresses were found in that file. "
                "Check the CSV has one address per row.",
                "danger",
            )
        elif invalid:
            flash(
                f"Uploaded {len(valid)} valid email(s). Skipped {len(invalid)} "
                f"row(s) that weren't valid email addresses.",
                "success",
            )
        else:
            flash(f"Uploaded {len(valid)} valid email(s) successfully!", "success")

        return redirect(url_for("upload"))

    emails = unique_emails(EMAIL_CSV)
    stats = {
        "uploaded_files": 1 if os.path.exists(EMAIL_CSV) else 0,
        "total_emails": len(emails),
        "size_kb": file_size_kb(EMAIL_CSV),
    }
    return render_template("upload.html", stats=stats)


# ================================================================
# CLASSIFY PAGE
# ================================================================
@app.route("/classify", methods=["GET", "POST"])
def classify():
    if request.method == "POST":
        emails = unique_emails(EMAIL_CSV)

        if not emails:
            flash("No emails found. Please upload a database first.", "danger")
            return redirect(url_for("classify"))

        business, individual = classify_emails(emails)
        write_emails(BUSINESS_CSV, business)
        write_emails(INDIVIDUAL_CSV, individual)

        flash(
            f"Classification complete: {len(business)} business, "
            f"{len(individual)} individual.",
            "success",
        )
        return redirect(url_for("classify"))

    business = unique_emails(BUSINESS_CSV)
    individual = unique_emails(INDIVIDUAL_CSV)
    stats = {
        "business": len(business),
        "individual": len(individual),
        "total": len(business) + len(individual),
    }
    return render_template("classify.html", stats=stats)


# ================================================================
# SEND / CAMPAIGN PAGE
# ================================================================
def allowed_attachment(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_ATTACHMENT_EXT


def _run_notes(skipped_previously_sent, capped, daily_limit):
    """Build the extra sentence appended to the campaign-complete flash,
    surfacing duplicate-prevention and daily-limit effects rather than
    letting them happen silently."""
    parts = []
    if skipped_previously_sent:
        parts.append(f"Skipped {skipped_previously_sent} already-sent recipient(s).")
    if capped:
        parts.append(f"Capped at the daily limit of {daily_limit}; run again for the rest.")
    return (" " + " ".join(parts)) if parts else ""


@app.route("/send", methods=["GET", "POST"])
def send_mail():
    global report_data
    settings = load_settings()

    business = unique_emails(BUSINESS_CSV)
    individual = unique_emails(INDIVIDUAL_CSV)

    if request.method == "POST":
        subject = request.form.get("subject", "").strip() or settings["default_subject"]
        audience = request.form.get("audience", "all")
        body = request.form.get("message", "").strip() or settings["default_message"]

        if audience == "business":
            recipients = business
        elif audience == "individual":
            recipients = individual
        else:
            recipients = list(dict.fromkeys(business + individual))

        if not recipients:
            flash("No recipients found for the selected audience.", "danger")
            return redirect(url_for("send_mail"))

        # Duplicate prevention: cross-check against the send-history log
        # so a buyer already successfully emailed isn't contacted again
        # across runs. Toggle "Skip previously sent" off in Settings if
        # you actually want to re-send (e.g. a follow-up campaign).
        skipped_previously_sent = 0
        if settings.get("skip_previously_sent", True):
            confirmed_sent = set()
            if os.path.exists(SENT_LOG_CSV):
                with open(SENT_LOG_CSV, "r", newline="", encoding="utf-8") as f:
                    for row in csv.reader(f):
                        if len(row) >= 2 and row[1].startswith("sent"):
                            confirmed_sent.add(row[0].strip().lower())
            before = len(recipients)
            recipients = [r for r in recipients if r.lower() not in confirmed_sent]
            skipped_previously_sent = before - len(recipients)

        if not recipients:
            flash(
                "Every recipient in this audience has already been emailed "
                "successfully. Turn off \"Skip previously sent\" in Settings "
                "to re-send.",
                "danger",
            )
            return redirect(url_for("send_mail"))

        # Daily send limit — cap this run rather than blowing past a
        # configured ceiling; the operator can run again for the rest.
        daily_limit = DAILY_SEND_LIMIT
        capped = False
        if daily_limit and len(recipients) > daily_limit:
            recipients = recipients[:daily_limit]
            capped = True

        # Handle optional attachment
        attachment_bytes = None
        attachment_name = None
        file = request.files.get("attachment")
        if file and file.filename:
            if allowed_attachment(file.filename):
                attachment_bytes = file.read()
                attachment_name = file.filename
            else:
                flash("Attachment type not supported.", "danger")
                return redirect(url_for("send_mail"))

        sender_email = settings["email"] or EMAIL
        sender_pass = settings["app_password"] or APP_PASS
        try:
            delay = int(settings.get("delay", EMAIL_DELAY_SECONDS))
        except (TypeError, ValueError):
            delay = EMAIL_DELAY_SECONDS
        delay = max(0, delay)
        demo_mode = bool(settings.get("demo_mode"))

        report_data = {
            "total_emails": len(recipients),
            "success_count": 0,
            "failed_count": 0,
            "successful_emails": [],
            "failed_emails": [],
        }

        # ---------------- DEMO MODE ----------------
        # Simulates the full send flow without touching Gmail SMTP or
        # requiring any credentials. Every recipient is logged as "sent".
        if demo_mode:
            for receiver in recipients:
                report_data["success_count"] += 1
                report_data["successful_emails"].append(receiver)
                append_row(
                    SENT_LOG_CSV,
                    [receiver, "sent (demo)", time.strftime("%Y-%m-%d %H:%M:%S")],
                )

            note = _run_notes(skipped_previously_sent, capped, daily_limit)
            flash(
                f"Demo campaign complete: {report_data['success_count']} simulated sends. "
                f"No real emails were sent (Demo Mode is on in Settings).{note}",
                "success",
            )
            return redirect(url_for("report"))
        # --------------------------------------------

        if not sender_email or not sender_pass:
            flash(
                "Gmail credentials are not configured. Add them in Settings, "
                "or turn on Demo Mode to try the app without sending real emails.",
                "danger",
            )
            return redirect(url_for("send_mail"))

        try:
            smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
            smtp.login(sender_email, sender_pass)
        except Exception as e:
            flash(f"Could not connect to Gmail SMTP: {e}", "danger")
            return redirect(url_for("send_mail"))

        for receiver in recipients:
            try:
                msg = EmailMessage()
                msg["Subject"] = subject
                msg["From"] = sender_email
                msg["To"] = receiver
                if MONITOR_EMAIL:
                    msg["Cc"] = MONITOR_EMAIL
                msg.set_content(body)

                if attachment_bytes:
                    maintype = "application"
                    subtype = attachment_name.rsplit(".", 1)[-1]
                    msg.add_attachment(
                        attachment_bytes,
                        maintype=maintype,
                        subtype=subtype,
                        filename=attachment_name,
                    )

                try:
                    smtp.send_message(msg)
                except smtplib.SMTPServerDisconnected:
                    smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
                    smtp.login(sender_email, sender_pass)
                    smtp.send_message(msg)

                report_data["success_count"] += 1
                report_data["successful_emails"].append(receiver)
                append_row(SENT_LOG_CSV, [receiver, "sent", time.strftime("%Y-%m-%d %H:%M:%S")])
                time.sleep(delay)

            except Exception:
                report_data["failed_count"] += 1
                report_data["failed_emails"].append(receiver)
                append_row(SENT_LOG_CSV, [receiver, "failed", time.strftime("%Y-%m-%d %H:%M:%S")])

        try:
            smtp.quit()
        except Exception:
            pass

        flash(
            f"Campaign complete: {report_data['success_count']} sent, "
            f"{report_data['failed_count']} failed."
            f"{_run_notes(skipped_previously_sent, capped, daily_limit)}",
            "success",
        )
        return redirect(url_for("report"))

    stats = {
        "business": len(business),
        "individual": len(individual),
        "total": len(set(business + individual)),
    }
    return render_template("send_mail.html", stats=stats, settings=settings)


# ================================================================
# REPORT PAGE
# ================================================================
@app.route("/report")
def report():
    total = report_data["total_emails"]
    success = report_data["success_count"]
    failed = report_data["failed_count"]
    rate = round((success / total) * 100, 1) if total else 0

    return render_template(
        "report.html",
        report=report_data,
        rate=rate,
    )


@app.route("/download-report")
def download_report():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["email", "status"])
    for e in report_data["successful_emails"]:
        writer.writerow([csv_safe(e), "sent"])
    for e in report_data["failed_emails"]:
        writer.writerow([csv_safe(e), "failed"])

    mem = io.BytesIO(output.getvalue().encode("utf-8"))
    mem.seek(0)
    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="campaign_report.csv",
    )


# ================================================================
# SETTINGS PAGE
# ================================================================
@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    settings = load_settings()

    if request.method == "POST":
        settings["email"] = request.form.get("email", settings["email"])
        new_pass = request.form.get("app_password", "")
        if new_pass and set(new_pass) != {"*"}:
            settings["app_password"] = new_pass
        settings["default_subject"] = request.form.get(
            "default_subject", settings["default_subject"]
        )
        settings["default_message"] = request.form.get(
            "default_message", settings["default_message"]
        )
        try:
            settings["delay"] = int(request.form.get("delay", settings["delay"]) or EMAIL_DELAY_SECONDS)
        except (TypeError, ValueError):
            flash("Email delay must be a whole number of seconds — kept the previous value.", "danger")
            settings["delay"] = settings.get("delay", EMAIL_DELAY_SECONDS)
        settings["delay"] = max(0, settings["delay"])
        settings["auto_classify"] = bool(request.form.get("auto_classify"))
        settings["remove_duplicates"] = bool(request.form.get("remove_duplicates"))
        settings["skip_previously_sent"] = bool(request.form.get("skip_previously_sent"))
        settings["demo_mode"] = bool(request.form.get("demo_mode"))

        save_settings(settings)
        flash("Settings saved successfully!", "success")
        return redirect(url_for("settings_page"))

    display_settings = settings.copy()
    display_settings["app_password_masked"] = "*" * 16 if settings.get("app_password") else ""
    display_settings["smtp_connected"] = bool(settings.get("email") and settings.get("app_password"))
    display_settings["gemini_enabled"] = bool(secret_key)
    display_settings["demo_mode"] = settings.get("demo_mode", True)

    return render_template("settings.html", settings=display_settings)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
