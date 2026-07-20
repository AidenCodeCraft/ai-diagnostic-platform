"""API Key management service."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.api_key import ApiKey


class ApiKeyService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user_id: int, name: Optional[str] = None) -> Dict:
        raw = "ak-" + secrets.token_hex(24)
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        prefix = raw[:10]

        key = ApiKey(user_id=user_id, name=name or "default", key_hash=key_hash, prefix=prefix, is_active=True)
        self.db.add(key)
        self.db.commit()
        self.db.refresh(key)
        return {"id": key.id, "name": key.name, "prefix": prefix, "api_key": raw, "created_at": key.created_at.isoformat()}

    def list(self, user_id: int) -> List[ApiKey]:
        return self.db.query(ApiKey).filter(ApiKey.user_id == user_id).order_by(ApiKey.created_at.desc()).all()

    def revoke(self, key_id: int) -> None:
        key = self.db.query(ApiKey).filter(ApiKey.id == key_id).first()
        if not key:
            raise ValueError("api key not found")
        key.is_active = False
        self.db.commit()

    def verify(self, raw_key: str) -> Optional[int]:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key = self.db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active == True).first()
        if key:
            key.last_used_at = datetime.now(timezone.utc)
            self.db.commit()
            return key.user_id
        return None
