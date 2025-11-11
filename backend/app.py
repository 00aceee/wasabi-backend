from flask import Flask, send_from_directory
import os
from flask_cors import CORS
from backend.routes import auth_bp, bookings_bp, feedback_bp, admin_bp, staff_bp, services_bp

app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = "supersecretkey" 

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory('../marmu-react/public/assets', filename)

# Register blueprints with clear prefixes
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(bookings_bp, url_prefix="/bookings")
app.register_blueprint(feedback_bp, url_prefix="/feedback")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(staff_bp, url_prefix="/staff")
app.register_blueprint(services_bp, url_prefix="/services")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)