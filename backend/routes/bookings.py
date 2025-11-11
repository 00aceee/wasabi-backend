from flask import Blueprint, request, jsonify, session
from datetime import datetime
from backend.db import get_connection
from backend.utils.email_utils import send_appointment_status_email

bookings_bp = Blueprint("bookings", __name__)

@bookings_bp.route("", methods=["POST"])
def create_booking():
    data = request.get_json()
    required_fields = ["username", "fullname", "service", "date", "time", "staff_id"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    username = data["username"]
    fullname = data["fullname"]
    service = data["service"]
    date = data["date"]
    time = data["time"]
    staff_id = data["staff_id"]
    remarks = data.get("remarks", "")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT c.id FROM tbl_clients c JOIN tbl_accounts a ON c.account_id=a.id WHERE a.username=%s", (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404

        cursor.execute("SELECT s.fullname FROM tbl_staff s WHERE s.id=%s", (staff_id,))
        artist = cursor.fetchone()
        if not artist:
            return jsonify({"error": "Artist not found"}), 404
        artist_name = artist[0]

        cursor.execute("""
            SELECT id FROM tbl_appointment
            WHERE appointment_date=%s AND time=%s AND artist_id=%s AND status!='Cancelled'
        """, (date, time, staff_id))
        if cursor.fetchone():
            return jsonify({"error": "This time slot is already booked"}), 409

        try:
            cursor.execute("""
                SELECT COUNT(*) FROM tbl_appointment
                WHERE user_id=%s AND service=%s AND appointment_date>=DATE_SUB(CURDATE(), INTERVAL 14 DAY) AND status!='Cancelled'
            """, (user[0], service))
            recent_count = cursor.fetchone()[0]
            if recent_count and recent_count >= 1:
                return jsonify({"error": f"You can only book one {service} every 2 weeks."}), 400
        except Exception:
            pass

        cursor.execute("""
            INSERT INTO tbl_appointment
                (user_id, fullname, service, appointment_date, time, remarks, status, artist_id, artist_name)
            VALUES (%s, %s, %s, %s, %s, %s, 'Pending', %s, %s)
        """, (user[0], fullname, service, date, time, remarks, staff_id, artist_name))

        cursor.execute("""
            UPDATE tbl_staff_unavailability
            SET is_booked=TRUE
            WHERE staff_id=%s AND unavailable_date=%s AND unavailable_time=%s
        """, (staff_id, date, time))

        conn.commit()
        return jsonify({"message": "Booking created successfully!", "status": "Pending"}), 201
    except Exception as e:
        print("Error creating booking:", e)
        return jsonify({"error": "An error occurred while processing your request."}), 500
    finally:
        conn.close()


@bookings_bp.route("/user/<username>", methods=["GET"])
def get_user_appointments(username):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT a.id AS account_id, c.id AS client_id
            FROM tbl_accounts a
            JOIN tbl_clients c ON c.account_id=a.id
            WHERE a.username=%s
        """, (username,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404

        cursor.execute("""
            SELECT id, fullname, service, appointment_date, time, remarks,
                    status, artist_name FROM tbl_appointment
            WHERE user_id=%s
            ORDER BY appointment_date DESC, time DESC
        """, (user["client_id"],))
        appointments = cursor.fetchall()

        for apt in appointments:
            t = apt.get("time")
            if t:
                try:
                    try:
                        parsed = datetime.strptime(t.strip(), "%H:%M")
                    except ValueError:
                        parsed = datetime.strptime(t.strip(), "%I:%M %p")
                    apt["time"] = parsed.strftime("%I:%M %p")
                except Exception:
                    apt["time"] = t  

        return jsonify(appointments), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@bookings_bp.route("/<int:appointment_id>/cancel", methods=["POST"])
def cancel_appointment(appointment_id):
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    conn = get_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute("SELECT * FROM tbl_appointment WHERE id=%s", (appointment_id,))
        apt = cursor.fetchone()
        if not apt:
            return jsonify({'error': 'Appointment not found'}), 404

        cursor.execute("SELECT c.id AS client_id FROM tbl_accounts a JOIN tbl_clients c ON c.account_id=a.id WHERE a.username=%s", (username,))
        user_row = cursor.fetchone()
        if not user_row or apt['user_id'] != user_row['client_id']:
            return jsonify({'error': 'Not authorized to cancel this appointment'}), 403

        if apt['status'] in ('Cancelled', 'Completed', 'Abandoned', 'Done'):
            return jsonify({'error': 'Appointment already in a terminal state, cannot be cancelled'}), 400

        cursor.execute("UPDATE tbl_appointment SET status='Cancelled' WHERE id=%s", (appointment_id,))

        try:
            cursor.execute("""
                UPDATE tbl_staff_unavailability
                SET unavailable_time=NULL
                WHERE staff_id=%s AND unavailable_date=%s AND unavailable_time=%s
            """, (apt['artist_id'], apt['appointment_date'], apt['time']))
        except Exception:
            pass

        conn.commit()

        try:
            cursor.execute("""
                SELECT acc.email, c.fullname
                FROM tbl_clients c
                JOIN tbl_accounts acc ON c.account_id=acc.id
                WHERE c.id=%s
            """, (apt['user_id'],))
            u = cursor.fetchone()
            if u and u.get('email'):
                send_appointment_status_email(
                    email=u['email'],
                    fullname=u['fullname'],
                    status='Cancelled',
                    service=apt.get('service'),
                    appointment_date=apt.get('appointment_date'),
                    time=apt.get('time'),
                    artist_name=apt.get('artist_name')
                )
        except Exception:
            pass

        return jsonify({'message': 'Appointment cancelled successfully'}), 200
    except Exception as e:
        return jsonify({'error': f"Error while cancelling the appointment: {str(e)}"}), 500
    finally:
        conn.close()


@bookings_bp.route("/available_slots", methods=["GET"])
def get_available_slots():
    date = request.args.get("date")
    staff_id = request.args.get("staff_id")
    if not date or not staff_id:
        return jsonify({"error": "Missing parameters"}), 400

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT unavailable_time FROM tbl_staff_unavailability
        WHERE staff_id=%s AND unavailable_date=%s
        ORDER BY unavailable_time ASC
    """, (staff_id, date))
    rows = cursor.fetchall()
    unavailable_times = {row["unavailable_time"] for row in rows}

    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        weekday = dt.weekday()
    except Exception:
        cursor.close()
        conn.close()
        return jsonify({"available_times": []})

    # closed every sunday
    if weekday == 6:
        cursor.close()
        conn.close()
        return jsonify({"available_times": []})

    start_hour = 9
    end_hour = 17 if weekday == 5 else 21
    default_slots = [f"{h%12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
                     for h in range(start_hour, end_hour) for m in [0]]

    cursor.execute("""
        SELECT time FROM tbl_appointment
        WHERE appointment_date=%s AND artist_id=%s AND status!='Cancelled'
    """, (date, staff_id))
    booked = {row["time"] for row in cursor.fetchall()}

    unavailable_times_12hr = set([datetime.strptime(t, "%H:%M").strftime("%I:%M %p") for t in unavailable_times])
    booked_12hr = set([datetime.strptime(t, "%H:%M").strftime("%I:%M %p") for t in booked])
    all_unavailable = unavailable_times_12hr | booked_12hr

    available_times = [t for t in default_slots if t not in all_unavailable]

    cursor.close()
    conn.close()
    return jsonify({"available_times": available_times})