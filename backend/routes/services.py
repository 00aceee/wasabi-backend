from flask import Blueprint, jsonify, send_from_directory, request
import os

services_bp = Blueprint("services", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REACT_PUBLIC_PATH = os.path.join(BASE_DIR, "../../backend/public/assets")

@services_bp.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(REACT_PUBLIC_PATH, filename)

@services_bp.route("/images", methods=["GET"])
def get_service_images():
    tattoo_folder = os.path.join(REACT_PUBLIC_PATH, "tattoo_images")
    haircut_folder = os.path.join(REACT_PUBLIC_PATH, "haircut_images")

    def get_images(folder, service_type):
        images = []
        if not os.path.exists(folder):
            return []
        for filename in os.listdir(folder):
            if filename.lower().endswith(".png"):
                name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
                # Use request.host_url instead of localhost
                image_url = f"{request.host_url}api/services/assets/{service_type}_images/{filename}"
                images.append({"name": name, "image": image_url})
        return sorted(images, key=lambda x: x["name"])

    tattoos = get_images(tattoo_folder, "tattoo")
    haircuts = get_images(haircut_folder, "haircut")

    return jsonify({
        "tattoos": tattoos,
        "haircuts": haircuts,
        "total": len(tattoos) + len(haircuts)
    }), 200
