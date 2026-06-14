"""Thin HTTP routes for exam management — no business logic here."""

import logging
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services import exam_service
from backend.services.exam_service import AlreadyGeneratedError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["exams"])


class CreateExamRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    subject: str = Field(..., min_length=1, max_length=100)
    scheduled_at: datetime
    center_ids: list[str] = Field(..., min_length=1)


@router.get("/")
async def list_exams() -> dict:
    return await exam_service.list_exams()


@router.get("/{exam_id}")
async def get_exam(exam_id: str) -> dict:
    result = await exam_service.get_exam(exam_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": "Exam not found", "code": "NOT_FOUND"})
    return result


@router.post("/")
async def create_exam(body: CreateExamRequest) -> dict:
    return await exam_service.create_exam(
        name=body.name,
        subject=body.subject,
        scheduled_at=body.scheduled_at,
        center_ids=body.center_ids,
    )


@router.post("/{exam_id}/generate")
async def generate_papers(exam_id: str) -> dict:
    try:
        return await exam_service.generate_papers(exam_id)
    except AlreadyGeneratedError:
        return JSONResponse(
            status_code=409,
            content={"error": "Papers already generated for this exam", "code": "ALREADY_GENERATED"},
        )
