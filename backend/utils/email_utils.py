import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
from backend.db import db
from datetime import datetime

load_dotenv()

# SMTP config
SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")
BREVO_SMTP_LOGIN = os.getenv("BREVO_SMTP_LOGIN")
BREVO_SMTP_KEY = os.getenv("BREVO_SMTP_KEY")
SMTP_SERVER = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
SMTP_PORT = int(os.getenv("BREVO_SMTP_PORT", "587"))

# API config
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

def log_email(to_email, subject, html_body):
    db.emails.insert_one({
        "to_email": to_email,
        "subject": subject,
        "body": html_body,
        "sent_at": datetime.utcnow()
    })

def _send_html_email(to_email: str, subject: str, html_body: str):
    # Try SMTP first
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Marmu Barber & Tattoo Shop <{SENDER_EMAIL}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(BREVO_SMTP_LOGIN, BREVO_SMTP_KEY)
            server.send_message(msg)

        log_email(to_email, subject, html_body)
        return
    except Exception as smtp_error:
        print(f"[SMTP ERROR] {smtp_error}")

    # Fallback to Brevo API
    try:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "sender": {"name": "Marmu Barber & Tattoo Shop", "email": SENDER_EMAIL},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_body
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        log_email(to_email, subject, html_body)
    except requests.exceptions.RequestException as api_error:
        print(f"[BREVO API ERROR] {api_error}")

def send_email_otp(email: str, subject: str, otp: str, expiry_minutes: int = 5):
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #333; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: #333; padding: 30px; border-radius: 8px; border: 4px solid goldenrod;">
            <h2 style="color: goldenrod; text-align: center;">Marmu Barber & Tattoo Shop</h2>
            <p style="font-size: 16px; color: #fff;">Use the following OTP to proceed:</p>
            <div style="text-align: center; margin: 30px 0;">
                <span style="font-size: 32px; font-weight: bold; color: #ffffff; background-color: #333; padding: 15px 25px; border-radius: 4px; border: 2px solid goldenrod; letter-spacing: 5px;">
                    {otp}
                </span>
            </div>
            <p style="font-size: 14px; color: #ddd;">This code is valid for <strong>{expiry_minutes} minutes</strong>.</p>
        </div>
    </body>
    </html>
    """
    _send_html_email(email, subject, html_body)

def send_feedback_reply_email(to_email: str, username: str, reply: str):
    subject = "Reply to Your Feedback - Marmu Barber & Tattoo Shop"
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: #333; padding: 30px; border: 1px solid goldenrod; border-radius: 8px;">
            <h2 style="color: goldenrod; text-align: center;">Marmu Barber & Tattoo Shop</h2>
            <p style="font-size: 16px; color: #fff;">Hi {username},</p>
            <div style="background-color: #333; padding: 15px 20px; border: 2px solid goldenrod; border-radius: 5px; color: #fff;">
                <strong>Our Reply:</strong><br>{reply}
            </div>
            <p style="font-size: 12px; color: #999; text-align: center;">&copy; 2025 Marmu Barber & Tattoo Shop.</p>
        </div>
    </body>
    </html>
    """
    _send_html_email(to_email, subject, html_body)

def send_appointment_status_email(email, fullname, status, service=None, appointment_date=None, time=None, artist_name=None):
    subject = f"Your Appointment has been {status}"
    color = "#28a745" if str(status).lower() == "approved" else "#d9534f"
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background: #333; padding: 30px; border-radius: 8px; border: 4px solid goldenrod;">
            <h2 style="color: goldenrod; text-align: center;">Marmu Barber & Tattoo Shop</h2>
            <p style="font-size: 16px; color: #fff;">Hi {fullname},</p>
            <p style="font-size: 16px; color: #fff;">Your appointment has been <strong style="color: {color};">{status}</strong>.</p>
            <div style="background-color: #333; padding: 15px 20px; border-radius: 6px; border: 2px solid goldenrod; margin: 20px 0; color: #fff;">
                <p><strong>Service:</strong> {service or 'N/A'}</p>
                <p><strong>Artist:</strong> {artist_name or 'N/A'}</p>
                <p><strong>Date:</strong> {appointment_date or 'N/A'}</p>
                <p><strong>Time:</strong> {time or 'N/A'}</p>
            </div>
        </div>
    </body>
    </html>
    """
    _send_html_email(email, subject, html_body)
