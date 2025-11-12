# /routes/feedback.py
from flask import Blueprint, request, jsonify
from backend.db import get_db
from backend.utils.email_utils import send_feedback_reply_email
from datetime import datetime
from bson import ObjectId

feedback_bp = Blueprint("feedback", __name__)

# ---------------- GET FEEDBACK ---------------- #
@feedback_bp.route("", methods=["GET"])
def get_feedback():
    db = get_db()
    feedback_list = list(
        db.feedback.find({}, {"_id": 0}).sort("date_submitted", -1)
    )

    # Format the date for display
    for f in feedback_list:
        if "date_submitted" in f and isinstance(f["date_submitted"], datetime):
            f["date"] = f["date_submitted"].strftime("%Y-%m-%d %H:%M")
        else:
            f["date"] = f.get("date_submitted", "")
        f.pop("date_submitted", None)
        # Ensure ObjectIds are strings
        try:
            if isinstance(f.get("account_id"), ObjectId):
                f["account_id"] = str(f["account_id"])
        except Exception:
            pass

    return jsonify(feedback_list), 200


# ---------------- POST FEEDBACK ---------------- #
@feedback_bp.route("", methods=["POST"])
def post_feedback():
    data = request.get_json()
    username = data.get("username")
    stars = data.get("stars")
    message = data.get("message")

    if not username or not stars or not message:
        return jsonify({"error": "Missing fields"}), 400

    db = get_db()

    # Find user
    account = db.tbl_accounts.find_one({"username": username})
    if not account:
        return jsonify({"error": "User not found"}), 404

    feedback_doc = {
        "account_id": account["_id"],
        "username": username,
        "stars": int(stars),
        "message": message,
        "reply": "",
        "date_submitted": datetime.now()
    }

    try:
        db.feedback.insert_one(feedback_doc)
        return jsonify({"message": "Feedback submitted successfully!"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
