from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime
from io import BytesIO
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
    return text.strip()


def _has_value(value: Any) -> bool:
    return _clean(value) != ""


def pdf_last_pages_text(pdf_bytes: bytes, last_pages: int = 6) -> str:
    """
    Liest die letzten PDF-Seiten.
    Dort stehen häufig Telefonnummer, E-Mail und IBAN.
    """

    if not pdf_bytes:
        return ""

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        start = max(0, len(doc) - last_pages)

        parts: List[str] = []

        for i in range(start, len(doc)):
            parts.append(doc[i].get_text("text") or "")

        return "\n".join(parts)

    except Exception:
        pass

    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes))
        start = max(0, len(reader.pages) - last_pages)

        parts: List[str] = []

        for i in range(start, len(reader.pages)):
            parts.append(reader.pages[i].extract_text() or "")

        return "\n".join(parts)

    except Exception:
        return ""


def extract_handakte_extra(pdf_bytes: Optional[bytes]) -> Dict[str, str]:
    """
    Extrahiert nur Zusatzwerte für die Handakte:
    - MANDANT_TELEFON
    - MANDANT_EMAIL
    - MANDANT_IBAN
    """

    if not pdf_bytes:
        return {}

    text = pdf_last_pages_text(pdf_bytes, last_pages=6)

    if not text:
        return {}

    result: Dict[str, str] = {}

    section = text

    match = re.search(r"Ihre\s+Angaben(.+)$", text, flags=re.I | re.S)
    if match:
        section = match.group(1)

    # E-Mail
    email_match = re.search(
        r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}",
        section,
        flags=re.I,
    )

    if email_match:
        email = email_match.group(0).strip()
        result["MANDANT_EMAIL"] = email
        result["MANDANT_E_MAIL"] = email
        result["EMAIL"] = email
        result["E_MAIL"] = email

    # IBAN
    iban_match = re.search(
        r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b",
        section,
        flags=re.I,
    )

    if iban_match:
        iban = " ".join(iban_match.group(0).upper().split())
        result["MANDANT_IBAN"] = iban
        result["IBAN"] = iban

    # Telefonnummer
    phone_candidates = re.findall(
        r"(?<!\d)(?:\+49|0)[0-9][0-9\s\/\-\(\)]{5,}[0-9](?!\d)",
        section,
        flags=re.I,
    )

    cleaned_phones: List[str] = []

    for phone in phone_candidates:
        p = phone.strip()
        p = re.sub(r"[\s\/\-\(\)]", "", p)

        digits = re.sub(r"\D", "", p)

        if len(digits) >= 7 and p not in cleaned_phones:
            cleaned_phones.append(p)

    if cleaned_phones:
        phone = cleaned_phones[0]
        result["MANDANT_TELEFON"] = phone
        result["TELEFON"] = phone

        if re.match(r"^01[567]", phone):
            result["MANDANT_MOBILTELEFON"] = phone
            result["MOBILTELEFON"] = phone

    return result


def build_vorsteuer_kreuze(data: Dict[str, Any]) -> Dict[str, str]:
    raw = (
        data.get("VORSTEUERBERECHTIGUNG")
        or data.get("VORSTEUERABZUG")
        or data.get("VORSTEUER")
        or data.get("VORSTEUERABZUGSBERECHTIGT")
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


def build_handakte_context(
    data: Dict[str, Any],
    pdf_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Baut alle Platzhalterwerte für handakte_gutachten.docx.
    """

    extras = extract_handakte_extra(pdf_bytes)

    combined: Dict[str, Any] = dict(data)

    for key, value in extras.items():
        if _has_value(value) and not _has_value(combined.get(key)):
            combined[key] = value

    kreuze = build_vorsteuer_kreuze(combined)

    mandant_name = _clean(
        combined.get("MANDANT_NAME")
        or combined.get("MANDANT_VOLLNAME")
        or " ".join(
            x for x in [
                _clean(combined.get("MANDANT_VORNAME")),
                _clean(combined.get("MANDANT_NACHNAME")),
            ]
            if x
        )
    )

    telefon = _clean(
        combined.get("MANDANT_TELEFON")
        or combined.get("TELEFON")
        or combined.get("MANDANT_MOBILTELEFON")
        or combined.get("MOBILTELEFON")
    )

    email = _clean(
        combined.get("MANDANT_EMAIL")
        or combined.get("MANDANT_E_MAIL")
        or combined.get("EMAIL")
        or combined.get("E_MAIL")
    )

    iban = _clean(
        combined.get("MANDANT_IBAN")
        or combined.get("IBAN")
    )

    kennzeichen_gegner = _clean(
        combined.get("KENNZEICHEN_GEGENER")
        or combined.get("KENNZEICHEN_GEGNER")
        or combined.get("GEGNER_KENNZEICHEN")
    )

    context = {
        "HEUTEDATUM": (
            _clean(combined.get("HEUTEDATUM"))
            or _clean(combined.get("HEUTDATUM"))
            or datetime.now().strftime("%d.%m.%Y")
        ),

        "AKTENZEICHEN": _clean(combined.get("AKTENZEICHEN")),
        "SCHADENSNUMMER": _clean(combined.get("SCHADENSNUMMER")),

        "MANDANT_ANREDE": _clean(combined.get("MANDANT_ANREDE")),
        "MANDANT_VORNAME": _clean(combined.get("MANDANT_VORNAME")),
        "MANDANT_NACHNAME": _clean(combined.get("MANDANT_NACHNAME")),
        "MANDANT_NAME": mandant_name,
        "MANDANT_STRASSE": _clean(combined.get("MANDANT_STRASSE")),
        "MANDANT_PLZ_ORT": _clean(combined.get("MANDANT_PLZ_ORT")),

        "MANDANT_TELEFON": telefon,
        "MANDANT_EMAIL": email,
        "MANDANT_IBAN": iban,

        "VERSICHERUNG": _clean(combined.get("VERSICHERUNG")),
        "VER_STR": _clean(combined.get("VER_STR")) or _clean(combined.get("VER_STRASSE")),
        "VER_ORT": _clean(combined.get("VER_ORT")),

        # Deine Word-Datei nutzt aktuell diesen Schreibfehler:
        "KENNZEICHEN_GEGENER": kennzeichen_gegner,

        # Korrekte Variante zusätzlich, falls du die Vorlage später korrigierst:
        "KENNZEICHEN_GEGNER": kennzeichen_gegner,

        "ja_vstabzug": kreuze["ja_vstabzug"],
        "nicht_vstabzug": kreuze["nicht_vstabzug"],

        # Synonyme
        "TELEFON": telefon,
        "EMAIL": email,
        "E_MAIL": email,
        "IBAN": iban,
    }

    return context


def render_handakte_docx(
    data: Dict[str, Any],
    pdf_bytes: Optional[bytes] = None,
    template_path: str | Path = "handakte_gutachten.docx",
    output_dir: str | Path = "generated",
) -> Path:
    """
    Erstellt die fertige Handakte.
    """

    template_path = Path(template_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not template_path.exists():
        raise FileNotFoundError(f"Handakte-Vorlage nicht gefunden: {template_path}")

    context = build_handakte_context(
        data=data,
        pdf_bytes=pdf_bytes,
    )

    doc = DocxTemplate(str(template_path))
    doc.render(context)

    output_path = output_dir / f"handakte_{uuid.uuid4().hex}.docx"
    doc.save(str(output_path))

    return output_path
