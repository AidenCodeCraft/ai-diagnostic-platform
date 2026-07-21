"""Authentication service — registration, login, JWT management (no external deps)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.user import User


class AuthService:
    """Handles user registration, login, and JWT token operations."""

    _DEFAULT_SECRET = "ai-diagnostic-jwt-secret-change-in-production"

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, username: str, password: str, email: Optional[str] = None) -> User:
        existing = self.db.query(User).filter(User.username == username).first()
        if existing:
            raise ValueError("username already exists")
        if email:
            if self.db.query(User).filter(User.email == email).first():
                raise ValueError("email already registered")

        user = User(
            username=username,
            email=email,
            password_hash=self._hash_password(password),
            role="engineer",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> Dict[str, Any]:
        user = self.db.query(User).filter(User.username == username).first()
        if not user or not self._verify_password(password, user.password_hash or ""):
            raise ValueError("用户名或密码无效")
        if not user.is_active:
            raise ValueError("账户已禁用")
        return {
            "access_token": self._create_token(user),
            "token_type": "bearer",
            "user": user,
        }

    # ------------------------------------------------------------------
    # Token
    # ------------------------------------------------------------------

    def verify_token(self, token: str) -> Optional[int]:
        try:
            payload = self._decode_token(token)
            exp = payload.get("exp", 0)
            if exp < time.time():
                return None
            return payload.get("user_id")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # JWT (pure Python, no external deps)
    # ------------------------------------------------------------------

    def _create_token(self, user: User) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "exp": int(time.time()) + 86400,
            "iat": int(time.time()),
        }
        return self._encode(header, payload)

    def _decode_token(self, token: str) -> Dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("invalid token format")
        header_b64, payload_b64, sig_b64 = parts

        # Verify signature
        expected_sig = self._sign(header_b64 + "." + payload_b64)
        if not hmac.compare_digest(expected_sig, self._b64url_decode(sig_b64)):
            raise ValueError("invalid signature")

        payload_json = self._b64url_decode(payload_b64).decode()
        return json.loads(payload_json)

    def _encode(self, header: dict, payload: dict) -> str:
        header_b64 = self._b64url_encode(json.dumps(header).encode())
        payload_b64 = self._b64url_encode(json.dumps(payload).encode())
        sig = self._sign(header_b64 + "." + payload_b64)
        sig_b64 = self._b64url_encode(sig)
        return header_b64 + "." + payload_b64 + "." + sig_b64

    def _sign(self, data: str) -> bytes:
        return hmac.new(self._get_secret().encode(), data.encode(), hashlib.sha256).digest()

    def _get_secret(self) -> str:
        return os.getenv("JWT_SECRET", self._DEFAULT_SECRET)

    @staticmethod
    def _b64url_encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    @staticmethod
    def _b64url_decode(data: str) -> bytes:
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)

    # ------------------------------------------------------------------
    # Password hashing
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = os.urandom(16)
        hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
        return salt.hex() + ":" + hashed.hex()

    @staticmethod
    def _verify_password(password: str, stored: str) -> bool:
        try:
            salt_hex, hash_hex = stored.split(":")
            salt = bytes.fromhex(salt_hex)
            expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
            return hmac.compare_digest(expected.hex(), hash_hex)
        except (ValueError, AttributeError):
            return False

