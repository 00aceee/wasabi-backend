from flask import Blueprint, request, jsonify
from backend.db import get_connection
from backend.utils.security import hash_password
from backend.utils.email_utils import send_appointment_status_email
from backend.utils.email_utils import send_feedback_reply_email
import mysql.connector

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/dashboard-data", methods=["GET"])
def admin_dashboard_data():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) AS total_clients FROM tbl_clients")
        total_clients = cursor.fetchone().get('total_clients', 0)

        cursor.execute("SELECT COUNT(*) AS pending_appointments FROM tbl_appointment WHERE status='Pending'")
        pending = cursor.fetchone().get('pending_appointments', 0)

        cursor.execute("SELECT COUNT(*) AS new_feedback FROM tbl_feedback WHERE reply IS NULL OR reply=''")
        new_feedback = cursor.fetchone().get('new_feedback', 0)

        cursor.execute("""
            SELECT COALESCE(s.fullname, 'Unassigned') AS artist_name, COUNT(*) AS total_jobs
            FROM tbl_appointment a
            LEFT JOIN tbl_staff s ON a.artist_id=s.id
            WHERE a.status IN ('Completed','Done')
            GROUP BY artist_name
            ORDER BY total_jobs DESC
            LIMIT 10
        """)
        artist_performance = cursor.fetchall()

        return jsonify({
            "total_clients": total_clients,
            "notifications": {
                "pending_appointments": pending,
                "new_feedback": new_feedback
            },
            "artist_performance": artist_performance
        })
    finally:
        cursor.close()
        conn.close()

@admin_bp.route("/appointments/summary", methods=["GET"])
def appointments_summary():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                COUNT(*) AS totalAppointments,
                SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pendingAppointments,
                SUM(CASE WHEN status='Approved' THEN 1 ELSE 0 END) AS approvedAppointments
            FROM tbl_appointment
        """)
        summary = cursor.fetchone()
        return jsonify({
            "totalAppointments": summary["totalAppointments"] or 0,
            "pendingAppointments": summary["pendingAppointments"] or 0,
            "approvedAppointments": summary["approvedAppointments"] or 0
        })
    finally:
        cursor.close()
        conn.close()

@admin_bp.route("/appointments/monthly-report", methods=["GET"])
def monthly_report():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT service, COUNT(*) AS count
            FROM tbl_appointment
            WHERE appointment_date IS NOT NULL
              AND MONTH(appointment_date)=MONTH(CURRENT_DATE())
              AND YEAR(appointment_date)=YEAR(CURRENT_DATE())
            GROUP BY service
        """)
        rows = cursor.fetchall()
        result = {"haircut": 0, "tattoo": 0}
        for row in rows:
            key = (row["service"] or "").strip().lower()
            if key in result:
                result[key] = row["count"]
        return jsonify(result)
    finally:
        cursor.close()
        conn.close()

@admin_bp.route("/users", methods=["GET"])
def get_users():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    sort = request.args.get("sort", "name")
    filter_value = request.args.get("filter")
    offset = max(page - 1, 0) * per_page

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where_clauses, params = [], []
        if filter_value and filter_value != "all":
            where_clauses.append("a.role=%s")
            params.append(filter_value)
        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        sort_map = {
            "name": "fullname ASC",
            "name_desc": "fullname DESC",
            "username": "a.username ASC",
            "username_desc": "a.username DESC",
            "role": "a.role ASC",
            "role_desc": "a.role DESC",
        }
        order_sql = sort_map.get(sort, "fullname ASC")

        cursor.execute(f"""
            SELECT COUNT(*) AS total
            FROM tbl_accounts a
            LEFT JOIN tbl_clients c ON a.id=c.account_id
            LEFT JOIN tbl_staff s ON a.id=s.account_id
            LEFT JOIN tbl_admins ad ON a.id=ad.account_id
            {where_sql}
        """, tuple(params))
        total = cursor.fetchone()["total"]

        cursor.execute(f"""
            SELECT a.id, a.username, a.email, a.role,
                   COALESCE(c.fullname, s.fullname, ad.fullname) AS fullname
            FROM tbl_accounts a
            LEFT JOIN tbl_clients c ON a.id=c.account_id
            LEFT JOIN tbl_staff s ON a.id=s.account_id
            LEFT JOIN tbl_admins ad ON a.id=ad.account_id
            {where_sql}
            ORDER BY {order_sql}
            LIMIT %s OFFSET %s
        """, (*params, per_page, offset))
        data = cursor.fetchall()

        return jsonify({"data": data, "total": total, "page": page, "per_page": per_page})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/add_user', methods=['POST'])
def add_user():
    try:
        data = request.get_json()

        fullname = data.get('fullname')
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        role = data.get('role')

        # ✅ Validate required fields
        if not all([fullname, username, email, password, role]):
            return jsonify({"error": "Missing required fields"}), 400

        # ✅ Hash password
        password = hash_password(password)

        # ✅ Connect to database
        conn = get_connection()
        cursor = conn.cursor()

        # ✅ Insert into tbl_accounts
        query_account = """
            INSERT INTO tbl_accounts (username, email, hash_pass, role)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query_account, (username, email, password, role))
        account_id = cursor.lastrowid  # get the new account id

        # ✅ Insert into role-specific table
        if role.lower() == "client":
            cursor.execute(
                "INSERT INTO tbl_clients (account_id, fullname) VALUES (%s, %s)",
                (account_id, fullname)
            )
        elif role.lower() in ["barber", "tattooartist"]:
            cursor.execute(
                "INSERT INTO tbl_staff (account_id, fullname, specialization) VALUES (%s, %s, %s)",
                (account_id, fullname, role)
            )
        elif role.lower() == "admin":
            cursor.execute(
                "INSERT INTO tbl_admins (account_id, fullname) VALUES (%s, %s)",
                (account_id, fullname)
            )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "User added successfully"}), 201

    except mysql.connector.Error as db_err:
        print("❌ MySQL Error:", db_err)
        return jsonify({"error": str(db_err)}), 500
    except Exception as e:
        print("❌ Server Error:", e)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/appointments", methods=["GET"])
def get_appointments():
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    q = request.args.get('q')
    artist = request.args.get('artist')
    sort = request.args.get('sort', 'date')

    offset = max(page - 1, 0) * per_page
    status = (request.args.get('status') or '').strip().lower()
    exclude_history = request.args.get('exclude_history')
    history_only = request.args.get('history_only')

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        where_clauses, params = [], []

        if status and status != 'all':
            where_clauses.append("COALESCE(a.status, 'Pending')=%s")
            params.append(status.capitalize())
        elif history_only == '1':
            where_clauses.append("COALESCE(a.status, 'Pending') IN ('Completed','Abandoned','Cancelled')")
        elif exclude_history == '1':
            where_clauses.append("COALESCE(a.status, 'Pending') NOT IN ('Completed','Abandoned','Cancelled')")

        if q:
            like_q = f"%{q}%"
            where_clauses.append("""
                (a.fullname LIKE %s OR a.service LIKE %s OR 
                 a.artist_name LIKE %s OR CAST(a.id AS CHAR) LIKE %s)
            """)
            params.extend([like_q, like_q, like_q, like_q])

        if artist:
            where_clauses.append("a.artist_name=%s")
            params.append(artist.strip())

        where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        sort_map = {
            'date': 'a.appointment_date ASC, a.time ASC',
            'date_desc': 'a.appointment_date DESC, a.time DESC',
            'name': 'a.fullname ASC',
            'service': 'a.service ASC',
            'artist': 'a.artist_name ASC'
        }
        order_sql = sort_map.get(sort, sort_map['date'])

        cursor.execute(f"SELECT COUNT(*) AS total FROM tbl_appointment a {where_sql}", tuple(params))
        row = cursor.fetchone()
        total = row['total'] if row and 'total' in row else 0

        cursor.execute(f"""
            SELECT DISTINCT
                a.id, a.fullname, a.service, a.artist_name,
                a.appointment_date, a.time,
                COALESCE(a.status, 'Pending') AS status
            FROM tbl_appointment a
            {where_sql}
            ORDER BY {order_sql}
            LIMIT %s OFFSET %s
        """, (*params, per_page, offset))
        data = cursor.fetchall()

        return jsonify({"data": data, "total": total, "page": page, "per_page": per_page})
    finally:
        cursor.close()
        conn.close()

@admin_bp.route("/appointments/<int:appointment_id>", methods=["PUT"])
def update_appointment(appointment_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "Missing status field"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("UPDATE tbl_appointment SET status=%s WHERE id=%s", (new_status, appointment_id))
        conn.commit()

        cursor.execute("""
            SELECT a.fullname, acc.email, a.service, a.artist_name,
                   a.appointment_date, a.time
            FROM tbl_appointment a
            JOIN tbl_clients c ON a.user_id=c.id
            JOIN tbl_accounts acc ON c.account_id=acc.id
            WHERE a.id=%s
        """, (appointment_id,))
        user = cursor.fetchone()

        if user and new_status.lower() in ("approved", "denied"):
            send_appointment_status_email(
                email=user["email"],
                fullname=user["fullname"],
                status=new_status,
                artist_name=user["artist_name"],
                service=user["service"],
                appointment_date=user["appointment_date"],
                time=user["time"],
            )

        return jsonify({"message": f"Appointment #{appointment_id} updated to {new_status}"}), 200
    finally:
        cursor.close()
        conn.close()

@admin_bp.route("/feedback", methods=["GET"])
def get_feedback_admin():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        status = request.args.get('status')
        q = request.args.get('q')
        sort = request.args.get('sort', 'date')

        offset = max(page - 1, 0) * per_page

        conn = get_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        where_clauses = []
        params = []
        if status == 'resolved':
            where_clauses.append('resolved = 1')
        elif status == 'pending':
            where_clauses.append('resolved = 0')
        if q:
            like_q = f"%{q}%"
            where_clauses.append('(username LIKE %s OR message LIKE %s)')
            params.extend([like_q, like_q])

        where_sql = 'WHERE ' + ' AND '.join(where_clauses) if where_clauses else ''

        sort_map = {
            'date': "date_submitted DESC",
            'rating': "stars DESC"
        }
        order_sql = sort_map.get(sort, sort_map['date'])

        count_sql = f"SELECT COUNT(*) AS total FROM tbl_feedback {where_sql}"
        cursor.execute(count_sql, tuple(params))
        row = cursor.fetchone()
        total = row['total'] if row and 'total' in row else 0

        sql = f"""
            SELECT id, username AS user, stars, message, COALESCE(reply, '') AS reply,
                   resolved,
                   DATE_FORMAT(date_submitted, '%%Y-%%m-%%d %%H:%%i') AS date_submitted
            FROM tbl_feedback
            {where_sql}
            ORDER BY {order_sql}
            LIMIT %s OFFSET %s
        """
        exec_params = params + [per_page, offset]
        cursor.execute(sql, tuple(exec_params))
        feedback = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({"data": feedback, "total": total, "page": page, "per_page": per_page})
    except Exception as e:
        print("Error in get_feedback_admin:", e)
        return jsonify({"error": str(e)}), 500


@admin_bp.route("/feedback/<int:feedback_id>/reply", methods=["POST"])
def admin_reply_feedback(feedback_id):
    data = request.get_json()
    reply = data.get("reply")
    send_email = data.get("sendEmail", False)

    if not reply:
        return jsonify({"message": "Reply cannot be empty."}), 400

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT username, account_id FROM tbl_feedback WHERE id = %s", (feedback_id,))
        feedback = cursor.fetchone()
        if not feedback:
            return jsonify({"message": "Feedback not found."}), 404

        cursor.execute("""
            UPDATE tbl_feedback
            SET reply = %s, resolved = 1
            WHERE id = %s
        """, (reply, feedback_id))
        conn.commit()

        if send_email:
            cursor.execute("""
                SELECT acc.email 
                FROM tbl_clients c
                JOIN tbl_accounts acc ON c.account_id = acc.id
                WHERE c.id = %s
            """, (feedback["account_id"],))
            user = cursor.fetchone()
            if user and user["email"]:
                send_feedback_reply_email(user["email"], feedback["username"], reply)

        return jsonify({"message": "Reply saved successfully!"}), 200

    except Exception as e:
        print("Error in /admin/feedback/reply:", e)
        return jsonify({"message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@admin_bp.route("/feedback/<int:feedback_id>/resolve", methods=["POST"])
def toggle_feedback_resolved(feedback_id):
    data = request.get_json()
    resolved_status = 1 if data.get("resolved") else 0 

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE tbl_feedback
            SET resolved = %s
            WHERE id = %s
        """, (resolved_status, feedback_id))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"message": "Feedback not found."}), 404

        return jsonify({"message": f"Feedback status updated to resolved={resolved_status}"}), 200

    except Exception as e:
        print("Error in /admin/feedback/resolve:", e)
        return jsonify({"message": str(e)}), 500
    finally:
        if 'conn' in locals() and conn.is_connected():
            cursor.close()
            conn.close()