from flask import Blueprint, jsonify, send_from_directory, request, url_for
import os

services_bp = Blueprint("services", __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REACT_PUBLIC_PATH = os.path.join(BASE_DIR, "../../backend/public/assets")


# ---------------- SERVE STATIC ASSETS ---------------- #
@services_bp.route("/assets/<path:filename>")
def serve_assets(filename):
    """
    Serve static files from the public/assets folder.
    """
    return send_from_directory(REACT_PUBLIC_PATH, filename)


# ---------------- GET SERVICE IMAGES ---------------- #
@services_bp.route("/images", methods=["GET"])
def get_service_images():
    """
    Return all tattoo and haircut images with their URLs and formatted names.
    """
    tattoo_folder = os.path.join(REACT_PUBLIC_PATH, "tattoo_images")
    haircut_folder = os.path.join(REACT_PUBLIC_PATH, "haircut_images")

    def get_images(folder_path, service_type):
        images = []
        if not os.path.exists(folder_path):
            return images
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(".png"):
                name = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title()
                image_url = url_for("services.serve_assets",
                                    filename=f"{service_type}_images/{filename}",
                                    _external=True)
                images.append({"name": name, "image": image_url})
        return sorted(images, key=lambda x: x["name"])

    tattoos = get_images(tattoo_folder, "tattoo")
    haircuts = get_images(haircut_folder, "haircut")

    return jsonify({
        "tattoos": tattoos,
        "haircuts": haircuts,
        "total": len(tattoos) + len(haircuts)
    }), 200
