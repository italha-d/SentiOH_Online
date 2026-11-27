from __future__ import annotations
import hashlib
import hmac
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USERS_PATH = ROOT / "auth" / "users.json"
ITERATIONS = 200_000


def load_users():
    return json.loads(USERS_PATH.read_text(encoding="utf-8"))


def authenticate(username, password):
    username = str(username or "").strip().lower()
    user = next(
        (
            item for item in load_users()
            if item.get("username", "").lower() == username and item.get("enabled", True)
        ),
        None,
    )
    if not user:
        return None

    salt = bytes.fromhex(user["password_salt"])
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        ITERATIONS,
    ).hex()

    if not hmac.compare_digest(candidate, user["password_hash"]):
        return None

    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


def available_accounts():
    """Return enabled demo accounts without exposing password hashes or salts."""
    return [
        {
            "username": item["username"],
            "display_name": item["display_name"],
            "role": item["role"],
        }
        for item in load_users()
        if item.get("enabled", True)
    ]
