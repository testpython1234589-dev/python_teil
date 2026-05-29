from __future__ import annotations

import re
from typing import Dict, Any, List

from common import (
    clean_text,
    cleanup_name,
    extract_money,
)

# -------------------------
# Helper (übernommen aus schnur)
# -------------------------

def _get_lines(text: str) -> List[str]:
    return [clean_text(line) for line in str(text).splitlines() if clean_text(line)]


def _value_after_inline_label(lines: List[str], label: str) -> str:
    label_norm = clean_text(label).lower()

    for line in lines:
        line_clean = clean_text(line)
        if line_clean.lower().startswith(label_norm):
            return clean_text(line_clean[len(label):].strip(" :"))
    return ""


def _next_line_after_exact_label(lines: List[str], label: str) -> str:
    label_norm = clean_text(label).lower()

    for i, line in enumerate(lines):
        if clean_text(line).lower() == label_norm and i + 1 < len(lines):
            return clean_text(lines[i + 1])
    return ""

def _extract_header_anrede(lines: List[str]) -> str:
    """
    Schnur-Briefkopf, z. B.:
    Herr
    Hans-Peter Kliem
    Mobile Schlosserei
    ...
    Bei Rückfragen bitte
    """
    if not lines:
        return ""

    stop_markers = {
        "bei rückfragen bitte",
        "gutachten - nummer angeben!",
        "rechnungsnummer angeben!",
        "g u t a c h t e n",
        "r e c h n u n g",
    }

    for line in lines[:15]:
        txt = clean_text(line).strip().lower()

        if txt in stop_markers:
            break

        if txt == "herr":
            return "Herr"
        if txt == "frau":
            return "Frau"

    return ""

def _extract_block_between(text: str, start_label: str, next_label: str) -> str:
    if not text:
        return ""
    m = re.search(
        rf"{re.escape(start_label)}\s+(.+?)\s+{re.escape(next_label)}",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    return clean_text(m.group(1)) if m else ""


# -------------------------
# STOTKO PARSER
# -------------------------

def parse_stotko(pages: List[str], pdf_source=None) -> Dict[str, Any]:
    first_page = pages[0] if pages else ""
    full = "\n".join(pages)

    data: Dict[str, Any] = {}

    summary_lines = _get_lines(first_page)
    all_lines = _get_lines(full)

    # -------------------------
    # BASIS: bekannte Felder aus schnur übernehmen
    # -------------------------

    data["AKTENZEICHEN"] = _value_after_inline_label(all_lines, "Gutachtennummer") \
        or _value_after_inline_label(all_lines, "Aktenzeichen")

# MANDANT
    raw_name = _value_after_inline_label(base_lines, "Anspruchsteller")
    _, clean_name = cleanup_name(raw_name)

    anrede = (
        _extract_header_anrede_first_page(first_page)
        or _extract_header_anrede(summary_lines)
        or _extract_header_anrede(invoice_lines)
        or _extract_header_anrede(all_lines)

    )

    mandant_addr = ""
    for i, line in enumerate(base_lines):
        if clean_text(line).lower().startswith("anspruchsteller "):
            if i + 1 < len(base_lines):
                mandant_addr = base_lines[i + 1]
            break

    mandant_strasse, mandant_plz_ort = _split_street_plz_ort(mandant_addr)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name
    data["MANDANT_STRASSE"] = mandant_strasse
    data["MANDANT_PLZ_ORT"] = mandant_plz_ort


    # -------------------------
    # KENNZEICHEN
    # -------------------------

    data["KENNZEICHEN_MANDANT"] = _value_after_inline_label(all_lines, "Amtliches Kennzeichen")

    # STOTKO: Gegner oft anders benannt
    data["KENNZEICHEN_GEGNER"] = (
        _value_after_inline_label(all_lines, "Kennzeichen Unfallgegner")
        or _value_after_inline_label(all_lines, "Kennzeichen Gegner")
    )

    # -------------------------
    # VERSICHERUNG + ADRESSE (STOTKO SPEZIAL)
    # -------------------------

    data["VERSICHERUNG"] = _value_after_inline_label(all_lines, "Versicherung")

    vers_block = ""
    for i, line in enumerate(all_lines):
        if clean_text(line).lower().startswith("versicherung"):
            if i + 2 < len(all_lines):
                # STOTKO: Adresse oft 2-zeilig
                vers_block = all_lines[i + 1] + ", " + all_lines[i + 2]
            break

    if vers_block:
        if "," in vers_block:
            left, right = vers_block.split(",", 1)
            data["VER_STRASSE"] = clean_text(left)
            data["VER_ORT"] = clean_text(right)
        else:
            data["VER_STRASSE"] = vers_block
            data["VER_ORT"] = ""

    # -------------------------
    # SCHADENSNUMMER
    # -------------------------

    data["SCHADENSNUMMER"] = _value_after_inline_label(all_lines, "Schadennummer") \
        or _value_after_inline_label(all_lines, "Schaden-Nr.")

    # -------------------------
    # DATEN
    # -------------------------

    data["BESICHTIGUNGSDATUM"] = _value_after_inline_label(all_lines, "Besichtigungsdatum")

    # STOTKO: Unfalldatum oft anders
    data["UNFALL_DATUM"] = (
        _value_after_inline_label(all_lines, "Ereignis vom")
        or _value_after_inline_label(all_lines, "Unfalltag")
    )

    # -------------------------
    # FAHRZEUG
    # -------------------------

    typ = _value_after_inline_label(all_lines, "Typ / Untertyp")
    fabrikat = _value_after_inline_label(all_lines, "Fabrikat")

    data["FAHRZEUGTYP"] = clean_text(f"{fabrikat} {typ}".strip())

    # -------------------------
    # WERTE (STOTKO MAPPING DIFFERENZ)
    # -------------------------

    data["WERTMINDERUNG"] = extract_money(
        full,
        [
            r"Wertminderung.*?([0-9\.\,]+)",
            r"Wertminderung\s*\(MwSt[- ]neutral\)\s*EUR\s*([0-9\.\,]+)",
        ],
    )

    data["WBW"] = extract_money(
        full,
        [
            r"Wiederbeschaffungswert.*?([0-9\.\,]+)",
        ],
    )

    data["RESTWERT"] = extract_money(
        full,
        [
            r"Restwert.*?([0-9\.\,]+)",
        ],
    )

    # -------------------------
    # REPARATURKOSTEN (STOTKO)
    # -------------------------

    data["REPARATURKOSTEN_NETTO"] = extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.\s*EUR\s*([0-9\.\,]+)",
            r"Reparaturkosten netto\s*([0-9\.\,]+)",
        ],
    )

    # -------------------------
    # GUTACHTERKOSTEN (1. SEITE SPEZIAL)
    # -------------------------

    data["GUTACHTERKOSTEN_BRUTTO"] = extract_money(
        first_page,
        [
            r"Rechnungsbetrag brutto\s*EUR\s*([0-9\.\,]+)",
            r"Rechnungsbetrag inkl\.\s*MwSt.*?EUR\s*([0-9\.\,]+)",
        ],
    )

    # -------------------------
    # SCHADENHERGANG
    # -------------------------

    data["SCHADENHERGANG"] = _extract_block_between(
        full,
        "Schadenumfang:",
        "Bemerkung",
    )

    # -------------------------
    # FIX: geforderte Felder
    # -------------------------

    data.setdefault("WERTVERBESSERUNG", "")
    data.setdefault("UNFALL_UHRZEIT", "")
    data.setdefault("UNFALL_STRASSE", "")
    data.setdefault("UNFALL_ORT", "")

    data["_PARSER"] = "stotko"

    return data
