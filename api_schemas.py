from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExtractResponse(BaseModel):
    case_id: str
    status: str = "success"
    gutachter_key: Optional[str] = None
    template_key: Optional[str] = None
    case_type: Optional[str] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)


class GenerateWordRequest(BaseModel):
    case_id: Optional[str] = None
    template_file: str
    context: Dict[str, Any]


class GenerateWordResponse(BaseModel):
    status: str
    filename: str
    download_url: str


class HealthResponse(BaseModel):
    status: str
    service: str
