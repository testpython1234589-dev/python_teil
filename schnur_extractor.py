from __future__ import annotations

import re
from typing import Dict, Any, List

from common import (
    clean_text,
    cleanup_name,
    extract_money,
)


def _extract_block_between(text: str, start_label: str, next_label: str) -> str:
    if not text:
        return ""
    m = re.search(
        rf"{re.escape(start_label)}\s+(.+?)\s+{re.escape(next_label)}",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return clean_text(m.group(1))
    return ""


def _split_street_plz_ort(value: str) -> tuple[str, str]:
    value = clean_text(value)
    if not value:
        return "", ""

    if "," in value:
        left, right = value.split(",", 1)
        return clean_text(left), clean_text(right)

    m = re.match(r"^(.*?)(\d{5}\s+.+)$", value)
    if m:
        return clean_text(m.group(1)), clean_text(m.group(2))

    if re.search(r"\b\d{5}\b", value):
        return "", value

    return value, ""


def _get_lines(text: str) -> List[str]:
    return [clean_text(line) for line in str(text).splitlines() if clean_text(line)]


def _value_after_inline_label(lines: List[str], label: str) -> str:
    label_norm = clean_text(label).lower()

    for line in lines:
        line_clean = clean_text(line)
        line_lower = line_clean.lower()

        if line_lower.startswith(label_norm):
            value = line_clean[len(label):].strip(" :")
            return clean_text(value)

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


def parse_schnur(pages: List[str], pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data: Dict[str, Any] = {}

    p_invoice = ""
    p_summary = ""
    p_vehicle = ""
    p_unfall = ""
    p_schadenumfang = ""
    p_wbw = ""
    p_calc = ""

    for page in pages:
        lower = page.lower()

        if not p_invoice and "rechnung" in lower and "rechnungsbetrag inkl" in lower:
            p_invoice = page

        if not p_summary and "zusammenfassung des gutachtens" in lower:
            p_summary = page

        if not p_vehicle and "technische daten und fahrzeugbeschreibung" in lower:
            p_vehicle = page

        if not p_unfall and "unfallhergang" in lower:
            p_unfall = page

        if not p_schadenumfang and "schadenumfang" in lower:
            p_schadenumfang = page

        if not p_wbw and ("wiederbeschaffungswert" in lower or "restwert" in lower):
            p_wbw = page

        if not p_calc and "fahrzeughalter" in lower and "reparaturkosten-kalkulation" in lower:
            p_calc = page

    summary_lines = _get_lines(p_summary)
    invoice_lines = _get_lines(p_invoice)
    vehicle_lines = _get_lines(p_vehicle)
    calc_lines = _get_lines(p_calc)
    all_lines = _get_lines(full)

    base_lines = summary_lines or invoice_lines or all_lines

    # AKTENZEICHEN / GUTACHTENNUMMER
    aktenzeichen = (
        _next_line_after_exact_label(summary_lines, "Gutachten - Nummer angeben!")
        or _value_after_inline_label(invoice_lines, "Betreff Haftpflichtschaden -")
        or _next_line_after_exact_label(invoice_lines, "Gutachten - Nummer angeben!")
    )

    if aktenzeichen:
        m = re.search(r"\b(5[A-Z0-9]+)\b", aktenzeichen)
        data["AKTENZEICHEN"] = m.group(1) if m else clean_text(aktenzeichen)
    else:
        m = re.search(r"\b(5[A-Z0-9]+)\b", p_vehicle or "")
        data["AKTENZEICHEN"] = m.group(1) if m else ""

    # MANDANT
    raw_name = _value_after_inline_label(base_lines, "Anspruchsteller")
    _, clean_name = cleanup_name(raw_name)

    anrede = (
        _extract_header_anrede(summary_lines)
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

    # KENNZEICHEN
    data["KENNZEICHEN_MANDANT"] = _value_after_inline_label(base_lines, "Amtliches Kennzeichen")
    data["KENNZEICHEN_GEGNER"] = _value_after_inline_label(base_lines, "Kennzeichen Unfallgegner")

    # VERSICHERUNG
    data["VERSICHERUNG"] = _value_after_inline_label(base_lines, "Versicherung")

    vers_addr = ""
    for i, line in enumerate(base_lines):
        if clean_text(line).lower().startswith("versicherung "):
            if i + 1 < len(base_lines):
                vers_addr = base_lines[i + 1]
            break

    ver_strasse, ver_ort = _split_street_plz_ort(vers_addr)
    data["VER_STRASSE"] = ver_strasse
    data["VER_ORT"] = ver_ort

    # SCHADENSNUMMER / VERSICHERUNGSSCHEINNUMMER
    data["SCHADENSNUMMER"] = (
        _value_after_inline_label(base_lines, "Schadennummer")
        or _value_after_inline_label(invoice_lines, "Schadennummer")
        or _value_after_inline_label(base_lines, "Versicherungsscheinnummer")
        or _value_after_inline_label(invoice_lines, "Versicherungsscheinnummer")
        or _value_after_inline_label(invoice_lines, "Schaden- / Versicherungsscheinnummer")
    )

    data["VERSICHERUNGSSCHEINNUMMER"] = (
        _value_after_inline_label(base_lines, "Versicherungsscheinnummer")
        or _value_after_inline_label(invoice_lines, "Versicherungsscheinnummer")
    )

    # DATUM
    data["UNFALL_DATUM"] = _value_after_inline_label(base_lines, "Schadentag")
    data["BESICHTIGUNGSDATUM"] = _value_after_inline_label(base_lines, "Besichtigungsdatum")

    # FAHRZEUGTYP
    data["FAHRZEUGTYP"] = _value_after_inline_label(vehicle_lines, "Typ / Untertyp")

    # REPARATURKOSTEN / WBW / RESTWERT / WERTMINDERUNG
    data["REPARATURKOSTEN_NETTO"] = extract_money(
        p_summary + "\n" + p_calc + "\n" + full,
        [
            r"Reparaturkosten ohne MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Reparaturkosten netto\s*:\s*([0-9\.\,]+)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = extract_money(
        p_summary + "\n" + p_calc + "\n" + full,
        [
            r"Reparaturkosten geschätzt mit 19,00\s*%\s*MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Reparaturkosten geschätzt:\s*\(inkl\.\s*MwSt\.\)\s*EUR\s*([0-9\.\,]+)",
            r"Reparaturkosten mit 19,00\s*%\s*MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Reparaturkosten brutto\s*:\s*([0-9\.\,]+)",
        ],
    )

    data["WERTMINDERUNG"] = extract_money(
        p_summary + "\n" + p_wbw + "\n" + full,
        [
            r"Wertminderung\s+EUR\s+([0-9\.\,]+)",
            r"Merkantile Wertminderung:\s*EUR\s*([0-9\.\,]+)",
        ],
    )

    data["WBW"] = extract_money(
        p_summary + "\n" + p_wbw + "\n" + full,
        [
            r"Wiederbeschaffungswert \(differenzbesteuert\)\s+EUR\s+([0-9\.\,]+)",
            r"Wiederbeschaffungswert geschätzt:\s*\(differenzbesteuert\)\s*EUR\s*([0-9\.\,]+)",
            r"Wiederbeschaffungswert:\s*\(differenzbesteuert\)\s*EUR\s*([0-9\.\,]+)",
        ],
    )

    data["RESTWERT"] = extract_money(
        p_summary + "\n" + p_wbw + "\n" + full,
        [
            r"Restwert mit 19,00 % MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Restwert:\s*incl\.\s*MwSt\.\s*EUR\s*([0-9\.\,]+)",
        ],
    )

    # GUTACHTERKOSTEN
    data["GUTACHTERKOSTEN_NETTO"] = extract_money(
        p_invoice or full,
        [
            r"Rechnungsbetrag exkl\.\s*MwSt\s+EUR\s+([0-9\.\,]+)",
        ],
    )

    data["GUTACHTERKOSTEN_BRUTTO"] = extract_money(
        p_invoice or full,
        [
            r"Rechnungsbetrag inkl\.\s*MwSt\.\s+EUR\s+([0-9\.\,]+)",
        ],
    )

    # SCHNUR: meist keine explizite Vorsteuerangabe
    data["VORSTEUERABZUG_RAW"] = ""

    # SCHADENHERGANG + SCHADENUMFANG
    hergang = ""
    if p_unfall:
        hergang = _extract_block_between(p_unfall, "Unfallhergang:", "Blatt")
        if not hergang:
            hergang = _extract_block_between(p_unfall, "Unfallhergang", "Blatt")

    schadenumfang = ""
    if p_schadenumfang:
        schadenumfang = _extract_block_between(p_schadenumfang, "Schadenumfang:", "Bemerkung")
        if not schadenumfang:
            schadenumfang = _extract_block_between(p_schadenumfang, "Schadenumfang", "Bemerkung")
        if not schadenumfang:
            schadenumfang = _extract_block_between(p_schadenumfang, "Schadenumfang:", "Reparaturkosten")
        if not schadenumfang:
            schadenumfang = _extract_block_between(p_schadenumfang, "Schadenumfang", "Reparaturkosten")

    data["SCHADENHERGANG"] = clean_text("\n".join(x for x in [hergang, schadenumfang] if x))

    # DEFAULTS
    data.setdefault("UNFALL_UHRZEIT", "")
    data.setdefault("UNFALL_STRASSE", "")
    data.setdefault("UNFALL_ORT", "")
    data.setdefault("WERTVERBESSERUNG", "")
    data.setdefault("MELDUNGSKOSTEN_RAW", "")
    data.setdefault("ZUSATZKOSTEN1_NAME", "")
    data.setdefault("ZUSATZKOSTEN1_BETRAG", "")
    data.setdefault("ZUSATZKOSTEN2_NAME", "")
    data.setdefault("ZUSATZKOSTEN2_BETRAG", "")
    data.setdefault("ZUSATZKOSTEN3_NAME", "")
    data.setdefault("ZUSATZKOSTEN3_BETRAG", "")

    data["_PARSER"] = "schnur"
    return data
