import hashlib
import re

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def is_strong_password(password: str) -> bool:
    if not password or len(password) < 8:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit

def is_valid_email(email: str) -> bool:
    return re.match(r'^[a-zA-Z0-9._%+-]+@gmail\.com$', email or "") is not None
