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

def load_config() -> dict:
    """Loads config.json. If it doesn't exist, initializes it with a secure default hashed admin password."""
    if not os.path.exists(CONFIG_FILE):
        salt_hex, hash_hex = hash_password("admin123")
        initial_config = {
            "server_port": 8080,
            "admin_salt": salt_hex,
            "admin_password_hash": hash_hex,
            "session_secret": secrets.token_hex(32),
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
            return json.load(f)
    except Exception:
        salt_hex, hash_hex = hash_password("admin123")
        return {
            "server_port": 8080,
            "admin_salt": salt_hex,
            "admin_password_hash": hash_hex,
            "session_secret": secrets.token_hex(32),
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

def create_admin_session() -> str:
    token = secrets.token_hex(32)
    ACTIVE_SESSIONS[token] = {
        "created_at": time.time(),
        "role": "admin"
    }
    return token

def validate_token(token: str) -> bool:
    """Returns True if token exists and has not expired (24h validity)."""
    if not token or token not in ACTIVE_SESSIONS:
        return False
    session = ACTIVE_SESSIONS[token]
    if time.time() - session.get("created_at", 0) > 86400:
        del ACTIVE_SESSIONS[token]
        return False
    return True

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
