from flask import Blueprint, request, jsonify, session
from backend.db import get_connection
from backend.utils.security import hash_password, is_valid_email, is_strong_password
from backend.utils.email_utils import send_email_otp
from datetime import datetime, timedelta
import random

auth_bp = Blueprint("auth", __name__)

OTP_EXPIRY_MINUTES = 5
otp_storage = {}  

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username_or_email = data.get("username")
    password = data.get("password")
    if not username_or_email or not password:
        return jsonify({"error": "Username/Email and password required"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT a.id AS account_id, a.username, a.email, a.hash_pass, a.role,
               COALESCE(c.fullname, s.fullname, ad.fullname) AS fullname
        FROM tbl_accounts a
        LEFT JOIN tbl_clients c ON a.id = c.account_id
        LEFT JOIN tbl_staff s ON a.id = s.account_id
        LEFT JOIN tbl_admins ad ON a.id = ad.account_id
        WHERE a.username = %s OR a.email = %s
    """, (username_or_email, username_or_email))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user or hash_password(password) != user["hash_pass"]:
        return jsonify({"error": "Invalid username/email or password"}), 401

    session.update({
        "account_id": user["account_id"],
        "username": user["username"],
        "fullname": user["fullname"],
        "email": user["email"],
        "role": user["role"]
    })

    # Decide redirect target based on role
    redirect_url = "/"
    if user["role"].lower() in ["admin", "barber", "tattooartist", "staff"]:
        redirect_url = "/admin"
    else:
        redirect_url = "/dashboard"

    return jsonify({
        "user": {
            "account_id": user["account_id"],
            "username": user["username"],
            "fullname": user["fullname"],
            "email": user["email"],
            "role": user["role"]
        },
        "message": "Login successful",
        "redirect_url": redirect_url
    }), 200

@auth_bp.route("/change_password", methods=["POST"])
def change_password():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not all([current_password, new_password, confirm_password]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': 'Passwords do not match'}), 400
    if not is_strong_password(new_password):
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters and include letters and numbers'}), 400

    username = session['username']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT a.hash_pass FROM tbl_accounts a WHERE a.username = %s", (username,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        if hash_password(current_password) != row['hash_pass']:
            return jsonify({'success': False, 'message': 'Current password is incorrect'}), 403

        if hash_password(new_password) == row['hash_pass']:
            return jsonify({'success': False, 'message': 'New password must be different from the current password'}), 400

        cursor.close()
        cursor = conn.cursor()
        cursor.execute("UPDATE tbl_accounts SET hash_pass=%s WHERE username=%s",
                       (hash_password(new_password), username))
        conn.commit()
        return jsonify({'success': True, 'message': 'Password updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error updating password: {str(e)}'}), 500
    finally:
        conn.close()


@auth_bp.route('/send_otp', methods=['POST'])
def forgot_send_otp():
    email = request.json.get('email')
    if not email or not email.endswith('@gmail.com'):
        return jsonify({'success': False, 'message': 'Invalid email format'}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tbl_accounts WHERE email=%s", (email,))
        if not cursor.fetchone():
            return jsonify({'success': False, 'message': 'No account found with this email'}), 404
    finally:
        conn.close()

    otp = str(random.randint(100000, 999999))
    otp_storage[email] = {
        'otp': otp,
        'expires_at': datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    }

    try:
        send_email_otp(email, "Your OTP for Password Reset", otp)
        return jsonify({'success': True, 'message': 'OTP sent successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to send OTP: {str(e)}'}), 500
    
@auth_bp.route('/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    email, otp, new_pass, confirm = (
        data.get('email'),
        data.get('otp'),
        data.get('new_password'),
        data.get('confirm_password'),
    )

    if not all([email, otp, new_pass, confirm]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400
    if new_pass != confirm:
        return jsonify({'success': False, 'message': 'Passwords do not match'}), 400

    stored = otp_storage.get(email)
    if not stored or datetime.now() > stored['expires_at'] or otp != stored['otp']:
        return jsonify({'success': False, 'message': 'Invalid or expired OTP'}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tbl_accounts SET hash_pass=%s WHERE email=%s",
            (hash_password(new_pass), email)
        )
        conn.commit()
        del otp_storage[email]
        return jsonify({'success': True, 'message': 'Password reset successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
    finally:
        conn.close()

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

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM tbl_accounts WHERE username=%s OR email=%s", (username, email))
        if cursor.fetchone():
            return jsonify({"error": "Username or email already exists"}), 409

        role = "User"
        cursor.execute("""
            INSERT INTO tbl_accounts (username, email, hash_pass, role)
            VALUES (%s, %s, %s, %s)
        """, (username, email, hash_password(password), role))
        account_id = cursor.lastrowid

        cursor.execute("INSERT INTO tbl_clients (account_id, fullname) VALUES (%s, %s)", (account_id, fullname))
        conn.commit()

        del otp_storage[email]
        return jsonify({"message": "Signup successful!"}), 201
    except Exception as err:
        return jsonify({"error": f"Database error: {err}"}), 500
    finally:
        conn.close()

@auth_bp.route("/current_user", methods=["GET"])
def current_user():
    if 'username' in session:
        return jsonify({
            "user": {
                "username": session['username'],
                "fullname": session['fullname'],
                "email": session.get('email'),
                "role": session.get('role')
            }
        }), 200
    return jsonify({"error": "Not logged in"}), 401