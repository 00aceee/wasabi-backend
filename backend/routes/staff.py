from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId
from backend.db import get_db

staff_bp = Blueprint("staff", __name__)

# ---------------- COLLECTIONS ---------------- #
db = get_db()
accounts_col = db["accounts"]
staff_col = db["staff"]
unavailability_col = db["staff_unavailability"]


# ---------------- ADD STAFF UNAVAILABILITY ---------------- #
@staff_bp.route("/unavailability", methods=["POST"])
def add_unavailability():
    data = request.get_json()
    staff_id = data.get("staff_id")
    unavailable_date = data.get("unavailable_date")
    unavailable_times = data.get("unavailable_times", [])

    if not staff_id or not unavailable_date or not unavailable_times:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        # Convert staff_id to ObjectId if it's a string
        try:
            staff_obj_id = ObjectId(staff_id)
        except Exception:
            return jsonify({"error": "Invalid staff_id"}), 400

        # Remove existing entries for that date
        unavailability_col.delete_many({
            "staff_id": staff_obj_id,
            "unavailable_date": unavailable_date
        })

        # Insert new unavailable times
        documents = [
            {"staff_id": staff_obj_id, "unavailable_date": unavailable_date, "unavailable_time": t}
            for t in unavailable_times
        ]
        if documents:
            unavailability_col.insert_many(documents)

        return jsonify({"message": "Unavailability saved successfully"}), 201
    except Exception as e:
        return jsonify({"error": f"Failed to save unavailability: {str(e)}"}), 500


# ---------------- GET STAFF BY SERVICE ---------------- #
@staff_bp.route("/by-service/<service>", methods=["GET"])
def get_staff_by_service(service):
    service = service.lower()
    role_map = {"haircut": "Barber", "tattoo": "TattooArtist"}
    role = role_map.get(service)

    if not role:
        return jsonify([]), 200

    try:
        staff_list = list(staff_col.find({"role": role}, {"fullname": 1}))
        # Convert ObjectId to string
        for staff in staff_list:
            staff["id"] = str(staff["_id"])
            del staff["_id"]

        return jsonify(staff_list), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch staff: {str(e)}"}), 500


# ---------------- GET STAFF UNAVAILABILITY LIST ---------------- #
@staff_bp.route("/unavailability/list", methods=["GET"])
def get_staff_unavailability_list():
    try:
        pipeline = [
            {
                "$lookup": {
                    "from": "staff",
                    "localField": "staff_id",
                    "foreignField": "_id",
                    "as": "staff_info"
                }
            },
            {"$unwind": "$staff_info"},
            {
                "$project": {
                    "_id": 0,
                    "staff_id": {"$toString": "$staff_id"},
                    "unavailable_date": 1,
                    "unavailable_time": 1,
                    "staff_name": "$staff_info.fullname"
                }
            },
            {"$sort": {"unavailable_date": 1, "unavailable_time": 1}}
        ]
        results = list(unavailability_col.aggregate(pipeline))
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch unavailability: {str(e)}"}), 500
