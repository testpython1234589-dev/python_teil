from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from datetime import datetime
import uuid
import re

from docxtpl import DocxTemplate


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize(value: Any) -> str:
    text = _clean(value).lower()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    text = re.sub(r"\s+", " ", text)
    return text


def build_vorsteuer_kreuze(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Einfache Logik:

    Wenn VORSTEUERBERECHTIGUNG das Wort 'nicht' enthält:
        nicht_vstabzug = x
        ja_vstabzug = leer

    Sonst:
        ja_vstabzug = x
        nicht_vstabzug = leer
    """

    raw = (
        data.get("VORSTEUERBERECHTIGUNG")
        or data.get("VORSTEUERABZUG")
        or data.get("VORSTEUER")
        or ""
    )

    text = _normalize(raw)

    if "nicht" in text or "kein" in text or "keine" in text or "nein" in text:
        return {
            "ja_vstabzug": "",
            "nicht_vstabzug": "x",
        }

    return {
        "ja_vstabzug": "x",
        "nicht_vstabzug": "",
    }


def build_handakte_context(data: Dict[str, Any]) -> Dict[str, Any]:
    kreuze = build_vorsteuer_kreuze(data)

    context = {
        "HEUTEDATUM": _clean(data.get("HEUTEDATUM")) or _clean(data.get("HEUTDATUM")) or datetime.now().strftime("%d.%m.%Y"),

        "AKTENZEICHEN": _clean(data.get("AKTENZEICHEN")),

        "VERSICHERUNG": _clean(data.get("VERSICHERUNG")),
        "SCHADENSNUMMER": _clean(data.get("SCHADENSNUMMER")),

        "MANDANT_VORNAME": _clean(data.get("MANDANT_VORNAME")),
        "MANDANT_NACHNAME": _clean(data.get("MANDANT_NACHNAME")),
        "MANDANT_NAME": _clean(
            data.get("MANDANT_NAME")
            or data.get("MANDANT_VOLLNAME")
            or " ".join(
                x for x in [
                    _clean(data.get("MANDANT_VORNAME")),
                    _clean(data.get("MANDANT_NACHNAME")),
                ]
                if x
            )
        ),
        "MANDANT_STRASSE": _clean(data.get("MANDANT_STRASSE")),
        "MANDANT_PLZ_ORT": _clean(data.get("MANDANT_PLZ_ORT")),

        # Deine Vorlage nutzt VER_STR, dein Parser nutzt teilweise VER_STRASSE.
        "VER_STR": _clean(data.get("VER_STR")) or _clean(data.get("VER_STRASSE")),
        "VER_ORT": _clean(data.get("VER_ORT")),

        # Vorsteuer-Kreuze
        "ja_vstabzug": kreuze["ja_vstabzug"],
        "nicht_vstabzug": kreuze["nicht_vstabzug"],
    }

    return context


def render_handakte_docx(
    data: Dict[str, Any],
    template_path: str | Path = "handakte_gutachten.docx",
    output_dir: str | Path = "generated",
) -> Path:
    template_path = Path(template_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not template_path.exists():
        raise FileNotFoundError(f"Handakte-Vorlage nicht gefunden: {template_path}")

    context = build_handakte_context(data)

    doc = DocxTemplate(str(template_path))
    doc.render(context)

    output_path = output_dir / f"handakte_{uuid.uuid4().hex}.docx"
    doc.save(str(output_path))

    return output_path
