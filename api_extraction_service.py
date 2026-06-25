from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid
import sys

# Damit Python deine bestehenden Dateien im Repo-Root findet
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def normalize_result(raw: Any) -> Dict[str, Any]:
    """
    Vereinheitlicht unterschiedliche Rückgabeformate deines bestehenden Codes.
    Ziel: API soll immer gleiches JSON zurückgeben.
    """
    if raw is None:
        return {
            "case_type": None,
            "fields": {},
            "warnings": ["Extractor hat kein Ergebnis zurückgegeben."],
            "missing_fields": [],
        }

    if isinstance(raw, dict):
        fields = raw.get("fields") or raw.get("werte") or raw.get("context") or raw

        warnings = raw.get("warnings") or raw.get("hinweise") or []
        missing_fields = raw.get("missing_fields") or raw.get("fehlende_felder") or []
        case_type = raw.get("case_type") or raw.get("schadenart") or raw.get("typ")

        return {
            "case_type": case_type,
            "fields": fields if isinstance(fields, dict) else {},
            "warnings": warnings if isinstance(warnings, list) else [str(warnings)],
            "missing_fields": missing_fields if isinstance(missing_fields, list) else [str(missing_fields)],
        }

    return {
        "case_type": None,
        "fields": {},
        "warnings": [f"Unbekanntes Rückgabeformat: {type(raw).__name__}"],
        "missing_fields": [],
    }


def extract_values_from_pdf(
    pdf_path: Path,
    gutachter_key: Optional[str] = None,
    template_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Zentrale API-Funktion für PDF → Werte.
    Nutzt die echte Logik aus deiner Streamlit-App:
    gs.extract_from_pdf_bytes(...)
    wb.get_template_vars(...)
    gs.build_context(...)
    """

    try:
        import gutachten_service as gs
        import word_backend as wb

        # PDF als bytes lesen, weil dein bestehender Code pdf_bytes erwartet
        pdf_bytes = pdf_path.read_bytes()

        # API-Werte auf deine bestehenden Labels mappen
        normalized_gutachter = (gutachter_key or "gutachterexpress").strip().lower()

        template_label = map_template_label(template_key or "", normalized_gutachter)
        template_file = map_template_file(template_key or "", normalized_gutachter)

        # 1. echte Extraktion
        extracted = gs.extract_from_pdf_bytes(
            pdf_bytes,
            normalized_gutachter,
            template_label,
        )

        # 2. Template-Variablen aus Word lesen
        template_keys = sorted(list(wb.get_template_vars(template_file)))

        # 3. Kontext so bauen wie in Streamlit
        ctx = gs.build_context(set(template_keys), extracted)

        # 4. sinnvolle Warnungen sammeln
        warnings = []
        if not ctx:
            warnings.append("Kontext ist leer. Prüfe Template-Name und Extraktion.")

        missing_fields = [
            key for key in template_keys
            if str(ctx.get(key, "")).strip() == ""
        ]

        case_type = (
            extracted.get("SCHADENART")
            or extracted.get("_PARSER_VARIANTE")
            or extracted.get("_PARSER")
            or None
        )

        return {
            "case_id": str(uuid.uuid4()),
            "gutachter_key": normalized_gutachter,
            "template_key": template_key,
            "case_type": case_type,
            "fields": ctx,
            "warnings": warnings,
            "missing_fields": missing_fields,
        }

    except Exception as exc:
        return {
            "case_id": str(uuid.uuid4()),
            "gutachter_key": gutachter_key,
            "template_key": template_key,
            "case_type": None,
            "fields": {},
            "warnings": [f"Extraktion fehlgeschlagen: {exc}"],
            "missing_fields": [],
        }


def map_template_label(template_key: str, gutachter_key: str) -> str:
    """
    Wandelt API-template_key in das Label um,
    das dein bestehender gutachten_service erwartet.
    """

    key = (template_key or "").strip().lower()

    if "nfz_standard" in key or "nutzfahrzeuge_standard" in key:
        return "Nutzfahrzeuge Standard"

    if "nfz_totalschaden" in key or "nutzfahrzeuge_totalschaden" in key:
        return "Nutzfahrzeuge Totalschaden"

    if "totalschaden" in key:
        return "Schreiben Totalschaden"

    return "Standard Schreiben"


def map_template_file(template_key: str, gutachter_key: str) -> str:
    """
    Wandelt API-template_key in echten .docx-Dateinamen um.
    Wenn bereits .docx übergeben wurde, wird dieser direkt genutzt.
    """

    key = (template_key or "").strip()

    if key.endswith(".docx"):
        return key

    g = (gutachter_key or "gutachterexpress").strip().lower()

    if g in {"express", "gutachterexpress"}:
        if "totalschaden" in key.lower():
            return "vorlage_schreibentotalschaden-1-express.docx"
        return "vorlage_schreiben-1-express.docx"

    if g == "schnur":
        if "totalschaden" in key.lower():
            return "vorlage_schreibentotalschaden-1-schnur.docx"
        return "vorlage_schreiben-1-schnur.docx"

    if g == "stotko":
        if "totalschaden" in key.lower():
            return "vorlage_schreibentotalschaden-1-stotko.docx"
        return "vorlage_schreiben-1-stotko.docx"

    return "vorlage_schreiben-1-express.docx"
