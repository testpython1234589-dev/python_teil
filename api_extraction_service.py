from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import uuid
import sys

# Repo-Root in Python-Pfad aufnehmen,
# damit gutachten_service.py und word_backend.py gefunden werden.
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def map_template_label(template_key: str, gutachter_key: str) -> str:
    """
    Wandelt den API-template_key in das Label um,
    das dein bestehender gutachten_service.py erwartet.
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
    Wandelt den API-template_key in den echten .docx-Dateinamen um.
    Wenn bereits ein .docx-Dateiname übergeben wurde, wird dieser direkt genutzt.
    """

    key = (template_key or "").strip()

    if key.endswith(".docx"):
        return key

    key_lower = key.lower()
    g = (gutachter_key or "gutachterexpress").strip().lower()

    if g == "express":
        g = "gutachterexpress"

    if g == "gutachterexpress":
        if "totalschaden" in key_lower:
            return "vorlage_schreibentotalschaden-1-express.docx"
        return "vorlage_schreiben-1-express.docx"

    if g == "schnur":
        if "totalschaden" in key_lower:
            return "vorlage_schreibentotalschaden-1-schnur.docx"
        return "vorlage_schreiben-1-schnur.docx"

    if g == "stotko":
        if "totalschaden" in key_lower:
            return "vorlage_schreibentotalschaden-1-stotko.docx"
        return "vorlage_schreiben-1-stotko.docx"

    return "vorlage_schreiben-1-express.docx"


def extract_values_from_pdf(
    pdf_path: Path,
    gutachter_key: Optional[str] = None,
    template_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    API-Funktion: PDF -> extrahierte Werte.

    Nutzt deine bestehende funktionierende Streamlit-Logik:

    1. gutachten_service.extract_from_pdf_bytes(...)
    2. word_backend.get_template_vars(...)
    3. gutachten_service.build_context(...)

    Ergebnis:
    Die API gibt direkt den fertigen Word-Kontext zurück,
    damit Next.js später die Werte anzeigen, prüfen und bearbeiten kann.
    """

    try:
        import gutachten_service as gs
        import word_backend as wb

        # PDF als bytes lesen, weil dein bestehender Code pdf_bytes erwartet.
        pdf_bytes = pdf_path.read_bytes()

        # Gutachter-Key normalisieren.
        normalized_gutachter = (gutachter_key or "gutachterexpress").strip().lower()

        if normalized_gutachter == "express":
            normalized_gutachter = "gutachterexpress"

        # Template-Label für deine bestehende Extraktionslogik bestimmen.
        template_label = map_template_label(
            template_key or "",
            normalized_gutachter,
        )

        # Echten Word-Dateinamen bestimmen.
        template_file = map_template_file(
            template_key or "",
            normalized_gutachter,
        )

        # 1. Deine echte Extraktion aus gutachten_service.py
        extracted = gs.extract_from_pdf_bytes(
            pdf_bytes,
            normalized_gutachter,
            template_label,
        )

        if not isinstance(extracted, dict):
            extracted = {}

        # 2. Platzhalter aus Word-Vorlage lesen.
        template_keys = sorted(list(wb.get_template_vars(template_file)))

        # 3. Kontext für Word bauen.
        ctx = gs.build_context(set(template_keys), extracted)

        if not isinstance(ctx, dict):
            ctx = {}

        warnings = []

        if not extracted:
            warnings.append("Extraktion hat keine Rohwerte geliefert.")

        if not template_keys:
            warnings.append("Aus der Word-Vorlage wurden keine Platzhalter erkannt.")

        if not ctx:
            warnings.append(
                "Word-Kontext ist leer. Prüfe Template-Dateiname, Gutachter-Key und Extraktion."
            )

        missing_fields = [
            key for key in template_keys
            if str(ctx.get(key, "")).strip() == ""
        ]

        case_type = (
            extracted.get("SCHADENART")
            or extracted.get("_PARSER_VARIANTE")
            or extracted.get("_PARSER")
            or template_label
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
