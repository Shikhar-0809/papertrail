"""Forensics routes: upload analysis and report retrieval."""

import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.services.forensics_service import (
    FileTooLargeError,
    UnsupportedMimeError,
    get_report,
    list_reports,
    start_analysis,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/forensics", tags=["forensics"])


class AnalyzeResponse(BaseModel):
    report_id: str
    status: str


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(file: UploadFile = File(...)) -> AnalyzeResponse:
    try:
        report_id = await start_analysis(file)
        return AnalyzeResponse(report_id=report_id, status="processing")
    except FileTooLargeError:
        return JSONResponse(status_code=413, content={"error": "File too large. Maximum 15MB.", "code": "FILE_TOO_LARGE"})
    except UnsupportedMimeError:
        return JSONResponse(status_code=415, content={
            "error": "Unsupported file type. Upload JPEG, PNG, or WebP.",
            "code": "UNSUPPORTED_MIME",
        })


@router.get("/report/{report_id}")
async def get_report_endpoint(report_id: str) -> dict:  # type: ignore[return]
    report = await get_report(report_id)
    if report is None:
        return JSONResponse(status_code=404, content={"error": "Report not found", "code": "NOT_FOUND"})
    return report


@router.get("/reports")
async def list_reports_endpoint() -> dict:
    reports = await list_reports()
    return {"reports": reports, "total": len(reports)}
