from .auth import auth_bp
from .bookings import bookings_bp
from .feedback import feedback_bp
from .admin import admin_bp
from .staff import staff_bp
from  .services import services_bp

__all__ = ["auth_bp", "bookings_bp", "feedback_bp", "admin_bp", "staff_bp", "services_bp"]
