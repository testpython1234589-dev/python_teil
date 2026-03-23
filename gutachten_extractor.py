from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Iterable

from pypdf import PdfReader


def pdf_to_text(pdf_source: str | Path | bytes) -> str:
    if isinstance(pdf_source, (str, Path)):
        reader = PdfReader(str(pdf_source))
    else:
        reader = PdfReader(BytesIO(pdf_source))

    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")

    text = "\n".join(pages)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def first_match(text: str, patterns: Iterable[str], flags=re.IGNORECASE | re.MULTILINE) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            return m.group(1).strip()
    return ""


def extract_block(text: str, patterns: Iterable[str], flags=re.IGNORECASE | re.MULTILINE | re.DOTALL) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            value = m.group(1).strip()
            value = re.sub(r"\n{2,}", "\n", value)
            return value
    return ""


def normalize_money_str(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    value = value.replace("€", "").replace("EUR", "").replace(" ", "")
    value = value.replace(".", "").replace(",", ".")
    try:
        dec = Decimal(value)
        # zurück ins deutsche Format
        s = f"{dec:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return s
    except (InvalidOperation, ValueError):
        return ""


def money_to_decimal(value: str) -> Decimal | None:
    if not value:
        return None
    value = value.replace(".", "").replace(",", ".").replace("€", "").replace(" ", "")
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def format_decimal_de(value: Decimal) -> str:
    s = f"{value:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def split_name(full_name: str) -> tuple[str, str]:
    if not full_name:
        return "", ""
    parts = full_name.strip().split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


def normalize_yes_no(value: str) -> str:
    if not value:
        return ""
    v = value.strip().lower()
    if v in {"ja", "yes", "y", "true", "1"}:
        return "Ja"
    if v in {"nein", "no", "n", "false", "0"}:
        return "Nein"
    return value.strip()


def extract_all(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}

    # Wichtig: diese Patterns musst du auf deine PDFs anpassen
    patterns = {
        "MANDANT_NAME": [
            r"(?:Auftraggeber|Geschädigte(?:r)?|Anspruchsteller)[:\s]+([^\n]+)",
        ],
        "MANDANT_STRASSE": [
            r"(?:Adresse|Anschrift)[:\s]+([^\n,]+)",
        ],
        "MANDANT_PLZ_ORT": [
            r"(?:Adresse|Anschrift)[:\s]+[^\n,]+,\s*(\d{5}\s+[^\n]+)",
            r"\b(\d{5}\s+[A-ZÄÖÜa-zäöüß\- ]+)\b",
        ],
        "UNFALL_DATUM": [
            r"(?:Schadentag|Unfalltag|Unfalldatum)[:\s]+(\d{2}\.\d{2}\.\d{4})",
        ],
        "UNFALL_ORT": [
            r"(?:Unfallort|Schadenort)[:\s]+([^\n]+)",
        ],
        "UNFALL_STRASSE": [
            r"(?:Unfallstraße|Unfallstelle|Straße)[:\s]+([^\n]+)",
        ],
        "AKTENZEICHEN": [
            r"(?:Aktenzeichen|AZ)[:\s]+([^\n]+)",
        ],
        "KENNZEICHEN": [
            r"(?:Kennzeichen|amtl\. Kennzeichen)[:\s]+([A-ZÄÖÜ0-9\- ]+)",
        ],
        "FAHRZEUGTYP": [
            r"(?:Fahrzeugtyp|Fahrzeug|PKW)[:\s]+([^\n]+)",
        ],
        "VERSICHERUNG": [
            r"(?:Versicherung|gegnerische Versicherung)[:\s]+([^\n]+)",
        ],
        "VER_STRASSE": [
            r"(?:Versicherung|gegnerische Versicherung)[:\s]+[^\n]*\n([^\n,]+)",
        ],
        "VER_ORT": [
            r"(?:Versicherung|gegnerische Versicherung)[:\s]+[^\n]*\n[^\n,]+,\s*([^\n]+)",
        ],
        "SCHADENSNUMMER": [
            r"(?:Schadennummer|Schaden-Nr\.?|Claim)[:\s]+([^\n]+)",
        ],
        "VORSTEUERBERECHTIGUNG": [
            r"(?:Vorsteuerabzugsberechtigt|Vorsteuerberechtigung)[:\s]+([^\n]+)",
        ],
        "REPARATURKOSTEN": [
            r"(?:Reparaturkosten(?: brutto)?|Reparaturkostenaufwand)[:\s]+([\d\.\,]+)",
        ],
        "WERTMINDERUNG": [
            r"(?:Wertminderung|merkantile Wertminderung)[:\s]+([\d\.\,]+)",
        ],
        "GUTACHTERKOSTEN": [
            r"(?:Gutachterkosten|Sachverständigenkosten)[:\s]+([\d\.\,]+)",
        ],
        "WBW": [
            r"(?:Wiederbeschaffungswert)[:\s]+([\d\.\,]+)",
        ],
        "RESTWERT": [
            r"(?:Restwert)[:\s]+([\d\.\,]+)",
        ],
    }

    for key, pats in patterns.items():
        data[key] = first_match(text, pats)

    data["SCHADENHERGANG"] = extract_block(
        text,
        [
            r"(?:Schadenhergang|Unfallhergang)[:\s]+(.+?)(?:\n[A-ZÄÖÜ][^\n:]{2,40}:|\Z)",
        ],
    )

    # Geldwerte normalisieren
    for k in ["REPARATURKOSTEN", "WERTMINDERUNG", "GUTACHTERKOSTEN", "WBW", "RESTWERT"]:
        data[k] = normalize_money_str(str(data.get(k, "")))

    return data


def derive_fields(extracted: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}

    vorname, nachname = split_name(str(extracted.get("MANDANT_NAME", "")))
    d["MANDANT_VORNAME"] = vorname
    d["MANDANT_NACHNAME"] = nachname

    d["VORSTEUERBERECHTIGUNG"] = normalize_yes_no(str(extracted.get("VORSTEUERBERECHTIGUNG", "")))

    rep = money_to_decimal(str(extracted.get("REPARATURKOSTEN", "")))
    wm = money_to_decimal(str(extracted.get("WERTMINDERUNG", "")))
    gut = money_to_decimal(str(extracted.get("GUTACHTERKOSTEN", "")))

    total = Decimal("0.00")
    has_any = False
    for item in [rep, wm, gut]:
        if item is not None:
            total += item
            has_any = True

    d["KOSTENSUMME_X"] = format_decimal_de(total) if has_any else ""

    return d


def extract_from_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    text = pdf_to_text(pdf_bytes)
    extracted = extract_all(text)
    derived = derive_fields(extracted)
    return {**extracted, **derived}


def build_context_for_template(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    for key in template_keys:
        value = extracted.get(key, "")
        ctx[key] = "" if value is None else str(value)
    return ctx
