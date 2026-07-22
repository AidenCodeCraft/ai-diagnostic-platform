"""Project Management API."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.database import session as session_module
from app.schemas import ProjectCreate, ProjectResponse, ProjectUpdate, ProjectListResponse
from app.services import ProjectService


def get_db_session():
    db = session_module.create_session()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db_session)):
    return ProjectService(db).create(body.model_dump())


@router.get("", response_model=ProjectListResponse)
def list_projects(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db_session)):
    return ProjectService(db).list(page=page, page_size=page_size)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db_session)):
    try:
        return ProjectService(db).get(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db_session)):
    try:
        return ProjectService(db).update(project_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db_session)):
    try:
        ProjectService(db).delete(project_id)
        return Response(status_code=204)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
