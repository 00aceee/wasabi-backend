# /routes/bookings.py
from flask import Blueprint, request, jsonify, session
from datetime import datetime, timedelta
from backend.db import get_db
from pymongo import ReturnDocument
from backend.utils.email_utils import send_appointment_status_email
from bson import ObjectId

bookings_bp = Blueprint("bookings", __name__)

# ---------------- CREATE BOOKING ---------------- #
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

    db = get_db()

    # Find client and staff
    account = db.tbl_accounts.find_one({"username": username})
    if not account:
        return jsonify({"error": "User not found"}), 404

    client = db.clients.find_one({"account_id": account["_id"]})
    if not client:
        return jsonify({"error": "Client profile not found"}), 404

    staff = db.tbl_staff.find_one({"_id": ObjectId(staff_id)})
    if not staff:
        return jsonify({"error": "Artist not found"}), 404
    artist_name = staff["fullname"]

    # Check if slot already booked
    existing = db.appointments.find_one({
        "appointment_date": date,
        "time": time,
        "artist_id": staff["_id"],
        "status": {"$ne": "Cancelled"}
    })
    if existing:
        return jsonify({"error": "This time slot is already booked"}), 409

    # Prevent overbooking within 2 weeks
    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    recent = db.appointments.count_documents({
        "user_id": client["_id"],
        "service": service,
        "appointment_date": {"$gte": two_weeks_ago},
        "status": {"$ne": "Cancelled"}
    })
    if recent >= 1:
        return jsonify({"error": f"You can only book one {service} every 2 weeks."}), 400

    # Generate human-friendly appointment code
    seq_doc = db.counters.find_one_and_update(
        {"_id": "appointment"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    code_str = f"APT-{int(seq_doc.get('seq', 1)):06d}" if seq_doc else None

    # Create booking
    appointment = {
        "user_id": client["_id"],
        "fullname": fullname,
        "service": service,
        "appointment_date": date,
        "time": time,
        "remarks": remarks,
        "status": "Pending",
        "artist_id": staff["_id"],
        "artist_name": artist_name,
        "created_at": datetime.now(),
        "display_id": code_str
    }
    db.appointments.insert_one(appointment)

    # Mark slot as booked
    db.staff_unavailability.update_one(
        {"staff_id": staff["_id"], "unavailable_date": date, "unavailable_time": time},
        {"$set": {"is_booked": True}},
        upsert=True
    )

    return jsonify({"message": "Booking created successfully!", "status": "Pending"}), 201


# ---------------- GET USER APPOINTMENTS ---------------- #
@bookings_bp.route("/user/<username>", methods=["GET"])
def get_user_appointments(username):
    db = get_db()

    account = db.tbl_accounts.find_one({"username": username})
    if not account:
        return jsonify({"error": "User not found"}), 404

    client = db.clients.find_one({"account_id": account["_id"]})
    if not client:
        return jsonify({"error": "Client profile not found"}), 404

    appointments = list(db.appointments.find({"user_id": client["_id"]}).sort([
        ("appointment_date", -1),
        ("time", -1)
    ]))

    # Normalize fields for JSON
    for apt in appointments:
        # Time to 12h format if stored as 24h
        t = apt.get("time")
        if t:
            try:
                parsed = datetime.strptime(t.strip(), "%H:%M")
                apt["time"] = parsed.strftime("%I:%M %p")
            except Exception:
                apt["time"] = t

        # Convert ObjectIds and datetimes to strings
        try:
            apt["_id"] = str(apt["_id"])
        except Exception:
            pass
        # Friendly display id for UI
        apt["display_id"] = apt.get("display_id") or (apt.get("_id")[-6:] if apt.get("_id") else None)
        if isinstance(apt.get("user_id"), ObjectId):
            apt["user_id"] = str(apt["user_id"])
        if isinstance(apt.get("artist_id"), ObjectId):
            apt["artist_id"] = str(apt["artist_id"])
        if isinstance(apt.get("created_at"), datetime):
            apt["created_at"] = apt["created_at"].strftime("%Y-%m-%d %H:%M:%S")

    return jsonify(appointments), 200


# ---------------- CANCEL APPOINTMENT ---------------- #
@bookings_bp.route("/<string:appointment_id>/cancel", methods=["POST"])
def cancel_appointment(appointment_id):
    if "username" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    username = session["username"]
    db = get_db()

    appointment = db.appointments.find_one({"_id": ObjectId(appointment_id)})
    if not appointment:
        return jsonify({"error": "Appointment not found"}), 404

    account = db.tbl_accounts.find_one({"username": username})
    client = db.clients.find_one({"account_id": account["_id"]})

    if not client or appointment["user_id"] != client["_id"]:
        return jsonify({"error": "Not authorized to cancel this appointment"}), 403

    if appointment["status"] in ["Cancelled", "Completed", "Abandoned", "Done"]:
        return jsonify({"error": "Appointment already in a terminal state"}), 400

    db.appointments.update_one({"_id": ObjectId(appointment_id)}, {"$set": {"status": "Cancelled"}})

    # Release slot
    db.staff_unavailability.update_one(
        {
            "staff_id": appointment["artist_id"],
            "unavailable_date": appointment["appointment_date"],
            "unavailable_time": appointment["time"]
        },
        {"$set": {"is_booked": False}}
    )

    # Send email
    user_account = db.tbl_accounts.find_one({"_id": account["_id"]})
    if user_account and user_account.get("email"):
        send_appointment_status_email(
            email=user_account["email"],
            fullname=session.get("fullname", ""),
            status="Cancelled",
            service=appointment.get("service"),
            appointment_date=appointment.get("appointment_date"),
            time=appointment.get("time"),
            artist_name=appointment.get("artist_name")
        )

    return jsonify({"message": "Appointment cancelled successfully"}), 200


# ---------------- AVAILABLE SLOTS ---------------- #
@bookings_bp.route("/available_slots", methods=["GET"])
def get_available_slots():
    date = request.args.get("date")
    staff_id = request.args.get("staff_id")
    if not date or not staff_id:
        return jsonify({"error": "Missing parameters"}), 400

    db = get_db()
    staff_oid = ObjectId(staff_id)

    # Combine explicitly set staff unavailability (any entry for the date)
    # and later we'll union with booked times from appointments.
    unavailable = list(db.staff_unavailability.find(
        {"staff_id": staff_oid, "unavailable_date": date},
        {"unavailable_time": 1, "_id": 0}
    ))
    unavailable_times = {u["unavailable_time"] for u in unavailable}

    dt = datetime.strptime(date, "%Y-%m-%d")
    weekday = dt.weekday()
    if weekday == 6:  # Sunday
        return jsonify({"available_times": []})

    start_hour = 9
    end_hour = 17 if weekday == 5 else 21
    default_slots = [f"{h%12 or 12}:00 {'AM' if h < 12 else 'PM'}" for h in range(start_hour, end_hour)]

    booked = list(db.appointments.find(
        {"appointment_date": date, "artist_id": staff_oid, "status": {"$ne": "Cancelled"}},
        {"time": 1, "_id": 0}
    ))
    booked_times = {b["time"] for b in booked}

    # Convert all to 12-hour format
    def to_12h(t):
        try:
            return datetime.strptime(t, "%H:%M").strftime("%I:%M %p")
        except Exception:
            return t

    all_unavailable = {to_12h(t) for t in (unavailable_times | booked_times)}
    available_times = [t for t in default_slots if t not in all_unavailable]

    return jsonify({"available_times": available_times})
