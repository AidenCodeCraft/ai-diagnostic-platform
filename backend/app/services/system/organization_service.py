"""Organization management service."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import Organization, OrganizationMember, User


class OrganizationService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, name: str, owner_id: int) -> Organization:
        org = Organization(name=name, owner_id=owner_id)
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)

        # Add owner as admin member
        member = OrganizationMember(organization_id=org.id, user_id=owner_id, role="admin")
        self.db.add(member)

        # Update user's org
        user = self.db.query(User).filter(User.id == owner_id).first()
        if user:
            user.organization_id = org.id

        self.db.commit()
        return org

    def get(self, org_id: int) -> Organization:
        org = self.db.query(Organization).filter(Organization.id == org_id).first()
        if not org:
            raise ValueError("organization not found")
        return org

    def list(self) -> list[Organization]:
        return self.db.query(Organization).all()

    def add_member(self, org_id: int, user_id: int, role: str = "engineer") -> OrganizationMember:
        existing = self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        ).first()
        if existing:
            existing.role = role
        else:
            existing = OrganizationMember(organization_id=org_id, user_id=user_id, role=role)
            self.db.add(existing)
        self.db.commit()
        return existing

    def get_members(self, org_id: int) -> list[OrganizationMember]:
        return self.db.query(OrganizationMember).filter(
            OrganizationMember.organization_id == org_id
        ).all()
