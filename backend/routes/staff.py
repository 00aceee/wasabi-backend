from flask import Blueprint, request, jsonify
from backend.db import get_connection

staff_bp = Blueprint("staff", __name__)

@staff_bp.route("/unavailability", methods=["POST"])
def add_unavailability():
    data = request.get_json()
    staff_id = data.get('staff_id')
    unavailable_date = data.get('unavailable_date')
    unavailable_times = data.get('unavailable_times', [])

    if not staff_id or not unavailable_date or not unavailable_times:
        return jsonify({"error": "Missing required fields"}), 400

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM tbl_staff_unavailability WHERE staff_id=%s AND unavailable_date=%s",
                       (staff_id, unavailable_date))
        for t in unavailable_times:
            cursor.execute("""
                INSERT INTO tbl_staff_unavailability (staff_id, unavailable_date, unavailable_time)
                VALUES (%s, %s, %s)
            """, (staff_id, unavailable_date, t))
        conn.commit()
        return jsonify({"message": "Unavailability saved successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@staff_bp.route("/by-service/<service>", methods=["GET"])
def get_staff_by_service(service):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        role = None
        if service.lower() == "haircut":
            role = "Barber"
        elif service.lower() == "tattoo":
            role = "TattooArtist"
        if not role:
            return jsonify([]), 200

        query = """
            SELECT a.id, s.fullname
            FROM tbl_accounts AS a
            JOIN tbl_staff AS s ON s.account_id = a.id
            WHERE a.role = %s AND s.specialization = %s
        """
        cursor.execute(query, (role, role))
        staff = cursor.fetchall()

        return jsonify(staff), 200
    except Exception as e:
        print("❌ Error in get_staff_by_service:", e)
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@staff_bp.route("/unavailability/list", methods=["GET"])
def get_staff_unavailability_list():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT tsu.*, s.fullname AS staff_name
            FROM tbl_staff_unavailability tsu
            JOIN tbl_staff s ON tsu.staff_id = s.id
        """)
        results = cursor.fetchall()
        return jsonify(results), 200
    finally:
        cursor.close()
        conn.close()
