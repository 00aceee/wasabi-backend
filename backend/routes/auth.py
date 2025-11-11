# /routes/auth.py
from flask import Blueprint, request, jsonify, session
from backend.db import get_db
from backend.utils.security import hash_password, is_valid_email, is_strong_password
from backend.utils.email_utils import send_email_otp
from datetime import datetime, timedelta
import random

auth_bp = Blueprint("auth", __name__)

OTP_EXPIRY_MINUTES = 5
otp_storage = {}  # In-memory OTP store

# ---------------- LOGIN ---------------- #
@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username_or_email = data.get("username")
    password = data.get("password")

    if not username_or_email or not password:
        return jsonify({"error": "Username/Email and password required"}), 400

    db = get_db()
    user = db.accounts.find_one(
        {"$or": [{"username": username_or_email}, {"email": username_or_email}]}
    )

    if not user or hash_password(password) != user.get("hash_pass"):
        return jsonify({"error": "Invalid username/email or password"}), 401

    # Get user's profile name
    fullname = None
    if user["role"].lower() == "user":
        client = db.clients.find_one({"account_id": user["_id"]})
        fullname = client["fullname"] if client else ""
    elif user["role"].lower() in ["barber", "tattooartist"]:
        staff = db.staff.find_one({"account_id": user["_id"]})
        fullname = staff["fullname"] if staff else ""
    elif user["role"].lower() == "admin":
        admin = db.admins.find_one({"account_id": user["_id"]})
        fullname = admin["fullname"] if admin else ""

    # Store session data
    session.update({
        "account_id": str(user["_id"]),
        "username": user["username"],
        "fullname": fullname,
        "email": user["email"],
        "role": user["role"]
    })

    redirect_url = "/admin" if user["role"].lower() in ["admin", "barber", "tattooartist", "staff"] else "/dashboard"

    return jsonify({
        "user": {
            "account_id": str(user["_id"]),
            "username": user["username"],
            "fullname": fullname,
            "email": user["email"],
            "role": user["role"]
        },
        "message": "Login successful",
        "redirect_url": redirect_url
    }), 200

# ---------------- CHANGE PASSWORD ---------------- #
@auth_bp.route("/change_password", methods=["POST"])
def change_password():
    if "username" not in session:
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    if not all([current_password, new_password, confirm_password]):
        return jsonify({"success": False, "message": "All fields are required"}), 400
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match"}), 400
    if not is_strong_password(new_password):
        return jsonify({
            "success": False,
            "message": "Password must be at least 8 characters and include letters and numbers"
        }), 400

    db = get_db()
    user = db.accounts.find_one({"username": session["username"]})
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    if hash_password(current_password) != user.get("hash_pass"):
        return jsonify({"success": False, "message": "Current password is incorrect"}), 403

    if hash_password(new_password) == user.get("hash_pass"):
        return jsonify({"success": False, "message": "New password must be different"}), 400

    db.accounts.update_one(
        {"_id": user["_id"]},
        {"$set": {"hash_pass": hash_password(new_password)}}
    )

    return jsonify({"success": True, "message": "Password updated successfully"})

# ---------------- FORGOT PASSWORD - SEND OTP ---------------- #
@auth_bp.route("/send_otp", methods=["POST"])
def forgot_send_otp():
    email = request.json.get("email")
    if not email or not email.endswith("@gmail.com"):
        return jsonify({"success": False, "message": "Invalid email format"}), 400

    db = get_db()
    if not db.accounts.find_one({"email": email}):
        return jsonify({"success": False, "message": "No account found with this email"}), 404

    otp = str(random.randint(100000, 999999))
    otp_storage[email] = {
        "otp": otp,
        "expires_at": datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    }

    try:
        send_email_otp(email, "Your OTP for Password Reset", otp)
        return jsonify({"success": True, "message": "OTP sent successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Failed to send OTP: {str(e)}"}), 500

# ---------------- RESET PASSWORD ---------------- #
@auth_bp.route("/reset_password", methods=["POST"])
def reset_password():
    data = request.json
    email, otp, new_pass, confirm = (
        data.get("email"),
        data.get("otp"),
        data.get("new_password"),
        data.get("confirm_password"),
    )

    if not all([email, otp, new_pass, confirm]):
        return jsonify({"success": False, "message": "All fields are required"}), 400
    if new_pass != confirm:
        return jsonify({"success": False, "message": "Passwords do not match"}), 400

    stored = otp_storage.get(email)
    if not stored or datetime.now() > stored["expires_at"] or otp != stored["otp"]:
        return jsonify({"success": False, "message": "Invalid or expired OTP"}), 400

    db = get_db()
    db.accounts.update_one(
        {"email": email},
        {"$set": {"hash_pass": hash_password(new_pass)}}
    )

    del otp_storage[email]
    return jsonify({"success": True, "message": "Password reset successful"})

# ---------------- SIGNUP - SEND OTP ---------------- #
@auth_bp.route("/signup/send_otp", methods=["POST"])
def signup_send_otp():
    data = request.get_json()
    email = data.get("email")
    if not email or not is_valid_email(email):
        return jsonify({"error": "Please enter a valid Gmail address"}), 400

    otp = str(random.randint(100000, 999999))
    otp_storage[email] = {"otp": otp, "expires": datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)}
    try:
        send_email_otp(email, "Your OTP for Signup", otp, OTP_EXPIRY_MINUTES)
        return jsonify({"message": "OTP sent successfully!"})
    except Exception as e:
        return jsonify({"error": f"Failed to send OTP: {e}"}), 500

# ---------------- SIGNUP - VERIFY ---------------- #
@auth_bp.route("/signup/verify", methods=["POST"])
def signup_verify():
    data = request.get_json()
    fullname = data.get("fullname")
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    confirm = data.get("confirm_password")
    otp = data.get("otp")

    if not all([fullname, username, email, password, confirm, otp]):
        return jsonify({"error": "All fields are required"}), 400
    if password != confirm:
        return jsonify({"error": "Passwords do not match"}), 400

    record = otp_storage.get(email)
    if not record or datetime.now() > record["expires"] or record["otp"] != otp:
        return jsonify({"error": "Invalid or expired OTP"}), 400

    db = get_db()
    if db.accounts.find_one({"$or": [{"username": username}, {"email": email}]}):
        return jsonify({"error": "Username or email already exists"}), 409

    role = "User"
    result = db.accounts.insert_one({
        "username": username,
        "email": email,
        "hash_pass": hash_password(password),
        "role": role
    })
    db.clients.insert_one({
        "account_id": result.inserted_id,
        "fullname": fullname
    })

    del otp_storage[email]
    return jsonify({"message": "Signup successful!"}), 201

# ---------------- CURRENT USER ---------------- #
@auth_bp.route("/current_user", methods=["GET"])
def current_user():
    if "username" in session:
        return jsonify({
            "user": {
                "username": session["username"],
                "fullname": session["fullname"],
                "email": session.get("email"),
                "role": session.get("role")
            }
        }), 200
    return jsonify({"error": "Not logged in"}), 401