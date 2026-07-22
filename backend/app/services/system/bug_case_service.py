"""Bug case service — historical bug tracking and solution retrieval."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import BugCase


class BugCaseService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: Dict[str, Any]) -> BugCase:
        bug = BugCase(**{k: v for k, v in data.items() if hasattr(BugCase, k)})
        self.db.add(bug)
        self.db.commit()
        self.db.refresh(bug)
        return bug

    def get(self, bug_id: int) -> BugCase:
        bug = self.db.query(BugCase).filter(BugCase.id == bug_id).first()
        if not bug:
            raise ValueError("bug case not found")
        return bug

    def list(self, page: int = 1, page_size: int = 20, category: Optional[str] = None, severity: Optional[str] = None) -> Dict[str, Any]:
        query = self.db.query(BugCase)
        if category:
            query = query.filter(BugCase.category == category)
        if severity:
            query = query.filter(BugCase.severity == severity)
        total = query.count()
        items = query.order_by(BugCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def update(self, bug_id: int, data: Dict[str, Any]) -> BugCase:
        bug = self.get(bug_id)
        for k, v in data.items():
            if hasattr(bug, k) and v is not None:
                setattr(bug, k, v)
        self.db.commit()
        self.db.refresh(bug)
        return bug

    def delete(self, bug_id: int) -> None:
        bug = self.get(bug_id)
        self.db.delete(bug)
        self.db.commit()

    def search(self, query: str, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        pattern = f"%{query}%"
        from sqlalchemy import or_
        q = self.db.query(BugCase).filter(
            or_(BugCase.title.ilike(pattern), BugCase.description.ilike(pattern), BugCase.root_cause.ilike(pattern))
        )
        total = q.count()
        items = q.order_by(BugCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": items, "total": total, "page": page, "page_size": page_size}
