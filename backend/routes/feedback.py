from flask import Blueprint, request, jsonify
from backend.db import get_connection
from backend.utils.email_utils import send_feedback_reply_email
from datetime import datetime

feedback_bp = Blueprint("feedback", __name__)

@feedback_bp.route("", methods=["GET"])
def get_feedback():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT username, stars, message, COALESCE(reply, '') AS reply,
               DATE_FORMAT(date_submitted, '%Y-%m-%d %H:%i') AS date
        FROM tbl_feedback
        ORDER BY date_submitted DESC
    """)
    feedback = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(feedback)

@feedback_bp.route("", methods=["POST"])
def post_feedback():
    data = request.get_json()
    username, stars, message = data.get("username"), data.get("stars"), data.get("message")
    if not username or not stars or not message:
        return jsonify({"error": "Missing fields"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM tbl_accounts WHERE username=%s", (username,))
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "User not found"}), 404

        account_id = result[0]
        cursor.execute("""
            INSERT INTO tbl_feedback (account_id, username, stars, message, date_submitted)
            VALUES (%s, %s, %s, %s, %s)
        """, (account_id, username, stars, message, datetime.now()))
        conn.commit()
        return jsonify({"message": "Feedback submitted successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
