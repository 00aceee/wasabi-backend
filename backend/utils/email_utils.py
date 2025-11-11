# /utils/email_utils.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv
from backend.db import db
from datetime import datetime

load_dotenv()

SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")
BREVO_SMTP_LOGIN = os.getenv("BREVO_SMTP_LOGIN")
BREVO_SMTP_KEY = os.getenv("BREVO_SMTP_KEY")
SMTP_SERVER = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com")
SMTP_PORT = int(os.getenv("BREVO_SMTP_PORT", "587"))

def log_email(to_email, subject, html_body):
    db.emails.insert_one({
        "to_email": to_email,
        "subject": subject,
        "body": html_body,
        "sent_at": datetime.utcnow()
    })

def _send_html_email(to_email: str, subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Marmu Barber & Tattoo Shop <{SENDER_EMAIL}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(BREVO_SMTP_LOGIN, BREVO_SMTP_KEY)
        server.send_message(msg)

def send_email_otp(email: str, subject: str, otp: str, expiry_minutes: int = 5):
    html_body = f"""
   {otp}
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
