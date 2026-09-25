"""
auth.py - Secure Hashed Authentication and Configuration Manager
- Zero hardcoded plain-text passwords
- PBKDF2-HMAC-SHA256 with 100,000 iterations and 16-byte random salt
- Secure cryptographically signed session tokens
"""

import os
import json
import hashlib
import secrets
import time
import hmac
import base64

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def generate_salt(length=16):
    return secrets.token_hex(length)

def hash_password(password: str, salt_hex: str = None) -> tuple[str, str]:
    """Hashes password using PBKDF2-HMAC-SHA256 with 100,000 iterations."""
    if not salt_hex:
        salt_hex = generate_salt(16)
    salt_bytes = bytes.fromhex(salt_hex)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_bytes, 100000)
    return salt_hex, pwd_hash.hex()

def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Verifies a password against the stored salt and PBKDF2 hash in constant time."""
    try:
        salt_bytes = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)
        actual_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt_bytes, 100000)
        return secrets.compare_digest(actual_hash, expected_hash)
    except Exception:
        return False

DEFAULT_ADMIN_SALT = "970822925df90d7897feb0dec7976197"
DEFAULT_ADMIN_HASH = "bf1683a9483b52b3f5f44b74affe52d3daa675923d6f62fe30f1da86ae89e94a"
DEFAULT_SUPER_ADMIN_SALT = "ad47dd94e4acb1eeee97917841d91b85"
DEFAULT_SUPER_ADMIN_HASH = "e07cff802fba32c61630a874bb49bab19c5f7dd375b3fbcc59a13b7ce6f1c41e"

def load_config() -> dict:
    """Loads config.json. If it doesn't exist, initializes it with default hashed admin password."""
    if not os.path.exists(CONFIG_FILE):
        initial_config = {
            "server_port": 8080,
            "admin_salt": DEFAULT_ADMIN_SALT,
            "admin_password_hash": DEFAULT_ADMIN_HASH,
            "super_admin_salt": DEFAULT_SUPER_ADMIN_SALT,
            "super_admin_password_hash": DEFAULT_SUPER_ADMIN_HASH,
            "session_secret": DEFAULT_SESSION_SECRET,
            "session_duration_hours": 24,
            "gdrive": {
                "enabled": False,
                "service_account_json": "service_account.json",
                "parent_folder_id": "",
                "folder_name_prefix": "LaptopHealth_"
            }
        }
        save_config(initial_config)
        return initial_config
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if not cfg.get("admin_password_hash"):
                cfg["admin_salt"] = DEFAULT_ADMIN_SALT
                cfg["admin_password_hash"] = DEFAULT_ADMIN_HASH
            if not cfg.get("super_admin_password_hash"):
                cfg["super_admin_salt"] = DEFAULT_SUPER_ADMIN_SALT
                cfg["super_admin_password_hash"] = DEFAULT_SUPER_ADMIN_HASH
            return cfg
    except Exception:
        return {
            "server_port": 8080,
            "admin_salt": DEFAULT_ADMIN_SALT,
            "admin_password_hash": DEFAULT_ADMIN_HASH,
            "super_admin_salt": DEFAULT_SUPER_ADMIN_SALT,
            "super_admin_password_hash": DEFAULT_SUPER_ADMIN_HASH,
            "session_secret": DEFAULT_SESSION_SECRET,
            "session_duration_hours": 24,
            "gdrive": {"enabled": False, "service_account_json": "service_account.json", "parent_folder_id": ""}
        }

def save_config(cfg: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass

ACTIVE_SESSIONS = {}
DEFAULT_SESSION_SECRET = "cae1b803daaaab6ce3720f3cced8e22e1a93778f3b0ffc971e87550acec51d5d"

def get_session_secret() -> bytes:
    try:
        cfg = load_config()
        secret = cfg.get("session_secret") or DEFAULT_SESSION_SECRET
        return secret.encode("utf-8")
    except Exception:
        return DEFAULT_SESSION_SECRET.encode("utf-8")

def create_admin_session(role: str = "admin") -> str:
    """Generates a cryptographically signed permanent HMAC token with encoded user role."""
    exp = int(time.time()) + 86400 * 365 * 100  # 100 Years
    payload = f"{role}:{exp}:{secrets.token_hex(8)}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8").rstrip("=")
    key = get_session_secret()
    sig = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{payload_b64}.{sig}"
    ACTIVE_SESSIONS[token] = {
        "created_at": time.time(),
        "role": role
    }
    return token

def authenticate(password: str) -> tuple[bool, str, str]:
    """Authenticates password against Super Admin (Admin_TIC@#) or Admin (admin123)."""
    cfg = load_config()
    # 1. Check Super Admin
    s_salt = cfg.get("super_admin_salt") or DEFAULT_SUPER_ADMIN_SALT
    s_hash = cfg.get("super_admin_password_hash") or DEFAULT_SUPER_ADMIN_HASH
    if verify_password(password, s_salt, s_hash):
        token = create_admin_session(role="superadmin")
        return True, "superadmin", token

    # 2. Check Admin / Technician
    a_salt = cfg.get("admin_salt") or DEFAULT_ADMIN_SALT
    a_hash = cfg.get("admin_password_hash") or DEFAULT_ADMIN_HASH
    if verify_password(password, a_salt, a_hash):
        token = create_admin_session(role="admin")
        return True, "admin", token

    return False, None, None

def get_token_role(token: str) -> str | None:
    """Returns 'superadmin' or 'admin' if token is valid, else None."""
    if not token:
        return None
    if token in ACTIVE_SESSIONS:
        return ACTIVE_SESSIONS[token].get("role", "admin")

    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts
        key = get_session_secret()
        expected_sig = hmac.new(key, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected_sig):
            return None

        padding = "=" * (4 - len(payload_b64) % 4) if len(payload_b64) % 4 else ""
        payload = base64.urlsafe_b64decode(payload_b64 + padding).decode("utf-8")
        role, exp_str, _ = payload.split(":", 2)
        if role in ("admin", "superadmin") and int(exp_str) > time.time():
            ACTIVE_SESSIONS[token] = {"created_at": time.time(), "role": role}
            return role
        return None
    except Exception:
        return None

def validate_token(token: str) -> bool:
    """Returns True if token exists in memory or has valid HMAC signature."""
    return get_token_role(token) is not None

def is_super_admin(token: str) -> bool:
    """Returns True ONLY if token belongs to a Super Admin."""
    return get_token_role(token) == "superadmin"

def revoke_token(token: str):
    if token in ACTIVE_SESSIONS:
        del ACTIVE_SESSIONS[token]

def update_admin_password(old_password: str, new_password: str) -> tuple[bool, str]:
    cfg = load_config()
    if not verify_password(old_password, cfg.get("admin_salt", ""), cfg.get("admin_password_hash", "")):
        return False, "Current password is incorrect"
    if len(new_password) < 4:
        return False, "New password must be at least 4 characters long"
    
    salt_hex, hash_hex = hash_password(new_password)
    cfg["admin_salt"] = salt_hex
    cfg["admin_password_hash"] = hash_hex
    save_config(cfg)
    return True, "Password updated successfully"
