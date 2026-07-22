"""Project management service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import Project


class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, data: Dict[str, Any]) -> Project:
        project = Project(**{k: v for k, v in data.items() if hasattr(Project, k)})
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return project

    def get(self, project_id: int) -> Project:
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("project not found")
        return project

    def list(self, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        query = self.db.query(Project)
        total = query.count()
        items = query.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def update(self, project_id: int, data: Dict[str, Any]) -> Project:
        project = self.get(project_id)
        for k, v in data.items():
            if hasattr(project, k) and v is not None:
                setattr(project, k, v)
        self.db.commit()
        self.db.refresh(project)
        return project

    def delete(self, project_id: int) -> None:
        project = self.get(project_id)
        self.db.delete(project)
        self.db.commit()
