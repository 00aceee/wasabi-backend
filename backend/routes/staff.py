from flask import Blueprint, request, jsonify
from bson.objectid import ObjectId
from backend.db import get_db

staff_bp = Blueprint("staff", __name__)

# ---------------- COLLECTIONS ---------------- #
db = get_db()
accounts_col = db["tbl_accounts"]
staff_col = db["tbl_staff"]
unavailability_col = db["staff_unavailability"]


# ---------------- ADD STAFF UNAVAILABILITY ---------------- #
# Support both legacy and current frontend paths
@staff_bp.route("/unavailability", methods=["POST", "OPTIONS"])
@staff_bp.route("/availability", methods=["POST", "OPTIONS"])
def add_unavailability():
    # Handle CORS preflight explicitly if needed
    from flask import make_response
    if request.method == "OPTIONS":
        return make_response(('', 200))
    data = request.get_json(silent=True) or {}

    # Accept multiple key styles from frontend
    staff_id = data.get("staff_id") or data.get("staffId") or data.get("staff")
    unavailable_date = (
        data.get("unavailable_date")
        or data.get("date")
        or data.get("unavailableDate")
    )
    unavailable_times = (
        data.get("unavailable_times")
        or data.get("times")
        or data.get("unavailableTimes")
        or []
    )
    # Normalize times payload if it arrived as a string
    if isinstance(unavailable_times, str):
        try:
            import json as _json
            parsed = _json.loads(unavailable_times)
            if isinstance(parsed, list):
                unavailable_times = parsed
            else:
                unavailable_times = [str(parsed)]
        except Exception:
            unavailable_times = [t.strip() for t in unavailable_times.split(',') if t.strip()]

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
        cursor = staff_col.find({"specialization": role}, {"_id": 1, "fullname": 1})
        staff_list = []
        for doc in cursor:
            staff_list.append({
                "id": str(doc.get("_id")),
                "fullname": doc.get("fullname", "")
            })

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
                    "from": "tbl_staff",
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
