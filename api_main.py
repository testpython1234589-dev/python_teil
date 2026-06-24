from __future__ import annotations

from pathlib import Path
import shutil
import uuid
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.config import UPLOAD_DIR, GENERATED_DIR, ALLOWED_EXTENSIONS, MAX_UPLOAD_SIZE_MB
from api.schemas import ExtractResponse, GenerateWordRequest, GenerateWordResponse, HealthResponse
from api.services.extraction_service import extract_values_from_pdf
from api.services.word_service import generate_word_document


app = FastAPI(
    title="Gutachten Word API",
    description="API für Gutachten-Auswertung und Word-Vorlagenerstellung.",
    version="0.1.0",
)

# Für lokale Next.js-Tests.
# Später in Produktion exakt auf deine Domains begrenzen.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="gutachten-word-api")


def validate_pdf_upload(file: UploadFile) -> None:
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien sind erlaubt.")

    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail=f"Ungültiger Dateityp: {file.content_type}")


def save_upload_file(file: UploadFile) -> Path:
    validate_pdf_upload(file)

    safe_name = f"{uuid.uuid4().hex}.pdf"
    destination = UPLOAD_DIR / safe_name

    size = 0
    max_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024

    with destination.open("wb") as buffer:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break

            size += len(chunk)
            if size > max_bytes:
                try:
                    destination.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=f"Datei zu groß. Maximal erlaubt: {MAX_UPLOAD_SIZE_MB} MB.",
                )

            buffer.write(chunk)

    return destination


@app.post("/api/v1/extract", response_model=ExtractResponse)
def extract_endpoint(
    file: UploadFile = File(...),
    gutachter_key: Optional[str] = Form(default=None),
    template_key: Optional[str] = Form(default=None),
) -> ExtractResponse:
    """
    PDF hochladen und Werte als JSON zurückbekommen.
    Später wird diese Route von Next.js aufgerufen.
    """
    pdf_path = save_upload_file(file)

    result = extract_values_from_pdf(
        pdf_path=pdf_path,
        gutachter_key=gutachter_key,
        template_key=template_key,
    )

    return ExtractResponse(
        case_id=result.get("case_id"),
        gutachter_key=result.get("gutachter_key"),
        template_key=result.get("template_key"),
        case_type=result.get("case_type"),
        fields=result.get("fields", {}),
        warnings=result.get("warnings", []),
        missing_fields=result.get("missing_fields", []),
    )


@app.post("/api/v1/generate-word", response_model=GenerateWordResponse)
def generate_word_endpoint(payload: GenerateWordRequest) -> GenerateWordResponse:
    """
    Bestätigte/korrigierte Werte entgegennehmen und Word-Datei erzeugen.
    """
    try:
        docx_path = generate_word_document(
            template_file=payload.template_file,
            context=payload.context,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return GenerateWordResponse(
        status="success",
        filename=docx_path.name,
        download_url=f"/api/v1/download/{docx_path.name}",
    )


@app.get("/api/v1/download/{filename}")
def download_file(filename: str):
    """
    Word-Datei herunterladen.
    """
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Ungültiger Dateiname.")

    path = GENERATED_DIR / filename

    if not path.exists() or path.suffix.lower() != ".docx":
        raise HTTPException(status_code=404, detail="Datei nicht gefunden.")

    return FileResponse(
        path=str(path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@app.get("/api/v1/templates")
def list_templates():
    """
    Einfache Template-Liste.
    Später durch Datenbank/Organisation ersetzen.
    """
    templates = []

    for path in Path(".").glob("**/*.docx"):
        name = path.name
        if name.startswith("~$"):
            continue
        if "generated" in str(path).lower():
            continue

        templates.append(
            {
                "filename": name,
                "path": str(path),
            }
        )

    return {"templates": templates}
