"""Authentication service — login with brute-force protection, JWT management."""

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

from app.core.logging_config import get_logger
from app.models import User, LoginAttempt

logger = get_logger(__name__)


class AuthService:
    """Handles login with MAC-based brute-force protection and JWT tokens."""

    _DEFAULT_SECRET = "ai-diagnostic-jwt-secret-change-in-production"

    # Brute-force parameters
    INITIAL_MAX_ATTEMPTS = 5       # 前 5 次错误后锁定
    INITIAL_LOCK_MINUTES = 20      # 首次锁定 20 分钟
    CYCLE_LOCK_MINUTES = 60        # 循环锁定 1 小时
    CYCLE_ATTEMPTS = 1             # 循环阶段每次解锁仅 1 次尝试

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Login (with brute-force protection)
    # ------------------------------------------------------------------

    def login(self, username: str, password: str, mac_address: str) -> Dict[str, Any]:
        """Login with MAC-based brute-force protection.

        Raises ValueError with specific messages for different failure modes.
        """
        now = datetime.now(timezone.utc)

        # 1. Check brute-force lock
        lock_error = self._check_lock(mac_address, now)
        if lock_error:
            raise ValueError(lock_error)

        # 2. Verify credentials
        user = self.db.query(User).filter(User.username == username).first()
        if not user or not self._verify_password(password, user.password_hash or ""):
            self._record_failure(mac_address, username, now)
            logger.warning("Login failed: username=%s mac=%s", username, mac_address[:8])
            raise ValueError("用户名或密码错误")

        if not user.is_active:
            logger.warning("Login rejected: user=%s is inactive", username)
            raise ValueError("账户已禁用")

        # 3. Success — clear all attempt records for this MAC
        self._clear_attempts(mac_address)

        logger.info("Login successful: user=%s role=%s", user.username, user.role)

        return {
            "access_token": self._create_token(user),
            "token_type": "bearer",
            "user": user,
        }

    # ------------------------------------------------------------------
    # Brute-force protection
    # ------------------------------------------------------------------

    def _check_lock(self, mac_address: str, now: datetime) -> Optional[str]:
        """Check if MAC is currently locked. Returns error message or None."""
        record = (
            self.db.query(LoginAttempt)
            .filter(LoginAttempt.mac_address == mac_address)
            .order_by(LoginAttempt.locked_until.desc())
            .first()
        )

        if not record or not record.locked_until:
            return None

        # Ensure locked_until is timezone-aware for comparison
        locked = record.locked_until
        if locked.tzinfo is None:
            locked = locked.replace(tzinfo=timezone.utc)

        if now < locked:
            remaining = int((locked - now).total_seconds() / 60)
            return f"登录已被锁定，请在 {remaining} 分钟后重试"

        return None

    def _record_failure(self, mac_address: str, username: str, now: datetime):
        """Record a failed login attempt and apply lock if needed."""
        record = (
            self.db.query(LoginAttempt)
            .filter(LoginAttempt.mac_address == mac_address)
            .order_by(LoginAttempt.id.desc())
            .first()
        )

        if not record:
            # First failure for this MAC
            record = LoginAttempt(
                mac_address=mac_address,
                username=username,
                attempt_count=1,
                cycle_phase=0,
                last_attempt_at=now,
            )
            self.db.add(record)
        else:
            # If previously locked and now expired, this is the "1 attempt" in cycle phase
            locked = record.locked_until
            if locked and locked.tzinfo is None:
                locked = locked.replace(tzinfo=timezone.utc)
            was_locked = locked and locked <= now

            if was_locked and record.cycle_phase > 0:
                # Cycle phase: this was the 1 allowed attempt — failed → lock again
                record.attempt_count = 1
                record.locked_until = now + timedelta(minutes=self.CYCLE_LOCK_MINUTES)
                record.last_attempt_at = now
            else:
                record.attempt_count += 1
                record.last_attempt_at = now

                if record.cycle_phase == 0 and record.attempt_count >= self.INITIAL_MAX_ATTEMPTS:
                    # Initial phase: 5th failure → lock 20 min, enter cycle phase
                    record.locked_until = now + timedelta(minutes=self.INITIAL_LOCK_MINUTES)
                    record.cycle_phase = 1
                elif record.cycle_phase > 0 and record.attempt_count >= self.CYCLE_ATTEMPTS:
                    # Already in cycle: re-lock for 1 hour
                    record.locked_until = now + timedelta(minutes=self.CYCLE_LOCK_MINUTES)

        self.db.commit()

    def _clear_attempts(self, mac_address: str):
        """Clear all attempt records after successful login."""
        self.db.query(LoginAttempt).filter(
            LoginAttempt.mac_address == mac_address
        ).delete()
        self.db.commit()

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
    # Password hashing (PBKDF2-SHA256)
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
