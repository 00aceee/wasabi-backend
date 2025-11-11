# /routes/admin.py
from flask import Blueprint, request, jsonify
from backend.db import get_mongo_db  # Assume this returns a PyMongo database instance
from backend.utils.security import hash_password
from backend.utils.email_utils import send_appointment_status_email, send_feedback_reply_email
from bson import ObjectId
from datetime import datetime

admin_bp = Blueprint("admin", __name__)

# -----------------------------
# Route 1: Admin Dashboard Data
# -----------------------------
@admin_bp.route("/dashboard-data", methods=["GET"])
def admin_dashboard_data():
    db = get_mongo_db()
    
    total_clients = db.tbl_clients.count_documents({})
    pending = db.tbl_appointments.count_documents({"status": "Pending"})
    new_feedback = db.tbl_feedback.count_documents({"reply": {"$in": [None, ""]}})
    
    # Artist performance (top 10)
    pipeline = [
        {"$match": {"status": {"$in": ["Completed", "Done"]}}},
        {"$lookup": {"from": "tbl_staff", "localField": "artist_id", "foreignField": "_id", "as": "artist"}},
        {"$unwind": {"path": "$artist", "preserveNullAndEmptyArrays": True}},
        {"$group": {"_id": {"$ifNull": ["$artist.fullname", "Unassigned"]}, "total_jobs": {"$sum": 1}}},
        {"$sort": {"total_jobs": -1}},
        {"$limit": 10}
    ]
    artist_performance = [{"artist_name": a["_id"], "total_jobs": a["total_jobs"]} for a in db.tbl_appointments.aggregate(pipeline)]
    
    return jsonify({
        "total_clients": total_clients,
        "notifications": {"pending_appointments": pending, "new_feedback": new_feedback},
        "artist_performance": artist_performance
    })

# -----------------------------
# Route 2: Appointments Summary
# -----------------------------
@admin_bp.route("/appointments/summary", methods=["GET"])
def appointments_summary():
    db = get_mongo_db()
    
    pipeline = [
        {"$group": {
            "_id": None,
            "totalAppointments": {"$sum": 1},
            "pendingAppointments": {"$sum": {"$cond": [{"$eq": ["$status", "Pending"]}, 1, 0]}},
            "approvedAppointments": {"$sum": {"$cond": [{"$eq": ["$status", "Approved"]}, 1, 0]}}
        }}
    ]
    summary = list(db.tbl_appointments.aggregate(pipeline))
    summary = summary[0] if summary else {"totalAppointments": 0, "pendingAppointments": 0, "approvedAppointments": 0}
    
    return jsonify(summary)

# -----------------------------
# Route 3: Monthly Report
# -----------------------------
@admin_bp.route("/appointments/monthly-report", methods=["GET"])
def monthly_report():
    db = get_mongo_db()
    now = datetime.now()
    
    pipeline = [
        {"$match": {
            "appointment_date": {"$gte": datetime(now.year, now.month, 1), "$lt": datetime(now.year, now.month + 1, 1)}
        }},
        {"$group": {"_id": "$service", "count": {"$sum": 1}}}
    ]
    rows = list(db.tbl_appointments.aggregate(pipeline))
    
    result = {"haircut": 0, "tattoo": 0}
    for row in rows:
        key = (row["_id"] or "").strip().lower()
        if key in result:
            result[key] = row["count"]
    return jsonify(result)

# -----------------------------
# Route 4: Get Users
# -----------------------------
@admin_bp.route("/users", methods=["GET"])
def get_users():
    db = get_mongo_db()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    sort = request.args.get("sort", "name")
    filter_value = request.args.get("filter")
    
    query = {}
    if filter_value and filter_value != "all":
        query["role"] = filter_value
    
    sort_map = {
        "name": [("fullname", 1)],
        "name_desc": [("fullname", -1)],
        "username": [("username", 1)],
        "username_desc": [("username", -1)],
        "role": [("role", 1)],
        "role_desc": [("role", -1)],
    }
    sort_order = sort_map.get(sort, [("fullname", 1)])
    
    total = db.tbl_accounts.count_documents(query)
    users = list(db.tbl_accounts.find(query).sort(sort_order).skip((page-1)*per_page).limit(per_page))
    
    # Fill fullname from role-specific collection
    data = []
    for u in users:
        fullname = u.get("fullname")
        if not fullname:
            if u["role"].lower() == "client":
                client = db.tbl_clients.find_one({"account_id": u["_id"]})
                fullname = client.get("fullname") if client else ""
            elif u["role"].lower() in ["barber", "tattooartist"]:
                staff = db.tbl_staff.find_one({"account_id": u["_id"]})
                fullname = staff.get("fullname") if staff else ""
            elif u["role"].lower() == "admin":
                admin = db.tbl_admins.find_one({"account_id": u["_id"]})
                fullname = admin.get("fullname") if admin else ""
        data.append({
            "id": str(u["_id"]),
            "username": u.get("username"),
            "email": u.get("email"),
            "role": u.get("role"),
            "fullname": fullname
        })
    
    return jsonify({"data": data, "total": total, "page": page, "per_page": per_page})

# -----------------------------
# Route 5: Add User
# -----------------------------
@admin_bp.route('/add_user', methods=['POST'])
def add_user():
    data = request.get_json()
    fullname = data.get('fullname')
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role')
    
    if not all([fullname, username, email, password, role]):
        return jsonify({"error": "Missing required fields"}), 400
    
    db = get_mongo_db()
    hashed_password = hash_password(password)
    account_id = db.tbl_accounts.insert_one({
        "username": username,
        "email": email,
        "hash_pass": hashed_password,
        "role": role
    }).inserted_id
    
    if role.lower() == "client":
        db.tbl_clients.insert_one({"account_id": account_id, "fullname": fullname})
    elif role.lower() in ["barber", "tattooartist"]:
        db.tbl_staff.insert_one({"account_id": account_id, "fullname": fullname, "specialization": role})
    elif role.lower() == "admin":
        db.tbl_admins.insert_one({"account_id": account_id, "fullname": fullname})
    
    return jsonify({"message": "User added successfully"}), 201

# -----------------------------
# Route 6: Get Appointments
# -----------------------------
@admin_bp.route("/appointments", methods=["GET"])
def get_appointments():
    db = get_mongo_db()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    q = request.args.get('q')
    artist = request.args.get('artist')
    sort = request.args.get('sort', 'date')
    status = (request.args.get('status') or '').strip().capitalize()
    exclude_history = request.args.get('exclude_history')
    history_only = request.args.get('history_only')
    
    query = {}
    if status and status != 'All':
        query["status"] = status
    elif history_only == '1':
        query["status"] = {"$in": ["Completed", "Abandoned", "Cancelled"]}
    elif exclude_history == '1':
        query["status"] = {"$nin": ["Completed", "Abandoned", "Cancelled"]}
    
    if q:
        query["$or"] = [
            {"fullname": {"$regex": q, "$options": "i"}},
            {"service": {"$regex": q, "$options": "i"}},
            {"artist_name": {"$regex": q, "$options": "i"}},
            {"_id": {"$regex": q, "$options": "i"}}
        ]
    if artist:
        query["artist_name"] = artist
    
    sort_map = {
        'date': [("appointment_date", 1), ("time", 1)],
        'date_desc': [("appointment_date", -1), ("time", -1)],
        'name': [("fullname", 1)],
        'service': [("service", 1)],
        'artist': [("artist_name", 1)]
    }
    sort_order = sort_map.get(sort, [("appointment_date", 1)])
    
    total = db.tbl_appointments.count_documents(query)
    appointments = list(db.tbl_appointments.find(query).sort(sort_order).skip((page-1)*per_page).limit(per_page))
    for a in appointments:
        a["id"] = str(a["_id"])
    
    return jsonify({"data": appointments, "total": total, "page": page, "per_page": per_page})

# -----------------------------
# Route 7: Update Appointment
# -----------------------------
@admin_bp.route("/appointments/<appointment_id>", methods=["PUT"])
def update_appointment(appointment_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": "Missing status field"}), 400
    
    db = get_mongo_db()
    appointment = db.tbl_appointments.find_one_and_update(
        {"_id": ObjectId(appointment_id)},
        {"$set": {"status": new_status}},
        return_document=True
    )
    
    if appointment and new_status.lower() in ("approved", "denied"):
        client = db.tbl_clients.find_one({"_id": appointment["user_id"]})
        account = db.tbl_accounts.find_one({"_id": client["account_id"]}) if client else None
        if account:
            send_appointment_status_email(
                email=account["email"],
                fullname=client["fullname"],
                status=new_status,
                artist_name=appointment.get("artist_name"),
                service=appointment.get("service"),
                appointment_date=appointment.get("appointment_date"),
                time=appointment.get("time"),
            )
    
    return jsonify({"message": f"Appointment #{appointment_id} updated to {new_status}"}), 200

# -----------------------------
# Route 8: Get Feedback
# -----------------------------
@admin_bp.route("/feedback", methods=["GET"])
def get_feedback_admin():
    db = get_mongo_db()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 50))
    status = request.args.get('status')
    q = request.args.get('q')
    sort = request.args.get('sort', 'date')
    
    query = {}
    if status == 'resolved':
        query["resolved"] = True
    elif status == 'pending':
        query["resolved"] = False
    if q:
        query["$or"] = [{"username": {"$regex": q, "$options": "i"}}, {"message": {"$regex": q, "$options": "i"}}]
    
    sort_map = {
        'date': [("date_submitted", -1)],
        'rating': [("stars", -1)]
    }
    sort_order = sort_map.get(sort, [("date_submitted", -1)])
    
    total = db.tbl_feedback.count_documents(query)
    feedback = list(db.tbl_feedback.find(query).sort(sort_order).skip((page-1)*per_page).limit(per_page))
    for f in feedback:
        f["id"] = str(f["_id"])
        f["reply"] = f.get("reply", "")
    
    return jsonify({"data": feedback, "total": total, "page": page, "per_page": per_page})

# -----------------------------
# Route 9: Admin Reply Feedback
# -----------------------------
@admin_bp.route("/feedback/<feedback_id>/reply", methods=["POST"])
def admin_reply_feedback(feedback_id):
    data = request.get_json()
    reply = data.get("reply")
    send_email = data.get("sendEmail", False)
    
    if not reply:
        return jsonify({"message": "Reply cannot be empty."}), 400
    
    db = get_mongo_db()
    feedback = db.tbl_feedback.find_one_and_update(
        {"_id": ObjectId(feedback_id)},
        {"$set": {"reply": reply, "resolved": True}},
        return_document=True
    )
    
    if not feedback:
        return jsonify({"message": "Feedback not found."}), 404
    
    if send_email:
        client = db.tbl_clients.find_one({"account_id": feedback["account_id"]})
        if client:
            account = db.tbl_accounts.find_one({"_id": client["account_id"]})
            if account:
                send_feedback_reply_email(account["email"], feedback["username"], reply)
    
    return jsonify({"message": "Reply saved successfully!"}), 200

# -----------------------------
# Route 10: Toggle Feedback Resolved
# -----------------------------
@admin_bp.route("/feedback/<feedback_id>/resolve", methods=["POST"])
def toggle_feedback_resolved(feedback_id):
    data = request.get_json()
    resolved_status = bool(data.get("resolved", False))
    
    db = get_mongo_db()
    result = db.tbl_feedback.update_one({"_id": ObjectId(feedback_id)}, {"$set": {"resolved": resolved_status}})
    
    if result.matched_count == 0:
        return jsonify({"message": "Feedback not found."}), 404
    
    return jsonify({"message": f"Feedback status updated to resolved={resolved_status}"}), 200
