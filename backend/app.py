# app.py
from flask import Flask, send_from_directory
import os
from flask_cors import CORS
from backend.routes import auth_bp, bookings_bp, feedback_bp, admin_bp, staff_bp, services_bp
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# CORS: allow production frontend and common local dev origins
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://marmuappointmentsystem.netlify.app",
                "http://localhost:5173",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:3000",
            ]
        }
    },
    supports_credentials=True,
)

app.secret_key = "supersecretkey"

# Cross-site cookie settings for sessions (Netlify -> Render)
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory('../backend/public/assets', filename)

# Register blueprints with clear prefixes
app.register_blueprint(auth_bp, url_prefix="/api/auth")
app.register_blueprint(bookings_bp, url_prefix="/api/bookings")
app.register_blueprint(feedback_bp, url_prefix="/api/feedback")
app.register_blueprint(admin_bp, url_prefix="/api/admin")
app.register_blueprint(staff_bp, url_prefix="/api/staff")
app.register_blueprint(services_bp, url_prefix="/api/services")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
