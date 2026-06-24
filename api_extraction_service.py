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

    WICHTIG:
    Hier musst du ggf. den Funktionsaufruf an deinen bestehenden Code anpassen.
    """

    # Variante 1: Wenn dein gutachten_service eine zentrale Funktion hat
    try:
        import gutachten_service as gs

        # HIER ggf. anpassen:
        # Beispielhafte mögliche Namen:
        # raw = gs.process_gutachten(str(pdf_path), gutachter_key=gutachter_key, template_key=template_key)
        # raw = gs.extract_gutachten(str(pdf_path), gutachter_key, template_key)
        # raw = gs.run_extraction(str(pdf_path), gutachter_key, template_key)

        if hasattr(gs, "process_gutachten"):
            raw = gs.process_gutachten(str(pdf_path), gutachter_key=gutachter_key, template_key=template_key)
        elif hasattr(gs, "extract_gutachten"):
            raw = gs.extract_gutachten(str(pdf_path), gutachter_key, template_key)
        elif hasattr(gs, "run_extraction"):
            raw = gs.run_extraction(str(pdf_path), gutachter_key, template_key)
        else:
            raise AttributeError(
                "In gutachten_service.py wurde keine Funktion process_gutachten, "
                "extract_gutachten oder run_extraction gefunden."
            )

        normalized = normalize_result(raw)

    except Exception as exc:
        normalized = {
            "case_type": None,
            "fields": {},
            "warnings": [f"Extraktion fehlgeschlagen: {exc}"],
            "missing_fields": [],
        }

    return {
        "case_id": str(uuid.uuid4()),
        "gutachter_key": gutachter_key,
        "template_key": template_key,
        **normalized,
    }
