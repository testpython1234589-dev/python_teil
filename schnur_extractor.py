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


def _find_line_index(lines: List[str], label: str) -> int:
    label_norm = clean_text(label).lower()
    for i, line in enumerate(lines):
        if clean_text(line).lower() == label_norm:
            return i
    return -1


def _value_after_inline_label(lines: List[str], label: str) -> str:
    label_norm = clean_text(label).lower()
    for line in lines:
        line_clean = clean_text(line)
        line_lower = line_clean.lower()
        if line_lower.startswith(label_norm):
            return clean_text(line_clean[len(label):].strip(" :"))
    return ""


def _next_line_after_exact_label(lines: List[str], label: str) -> str:
    idx = _find_line_index(lines, label)
    if idx >= 0 and idx + 1 < len(lines):
        return lines[idx + 1]
    return ""


def _find_page_by_terms(pages: List[str], terms: List[str]) -> str:
    for page in pages:
        lower = page.lower()
        if all(term.lower() in lower for term in terms):
            return page
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

    for page in pages:
        lower = page.lower()

        if not p_invoice and "rechnung" in lower and "rechnungsbetrag inkl. mwst" in lower:
            p_invoice = page

        if not p_summary and "zusammenfassung des gutachtens" in lower:
            p_summary = page

        if not p_vehicle and "technische daten und fahrzeugbeschreibung" in lower:
            p_vehicle = page

        if not p_unfall and "unfallhergang" in lower:
            p_unfall = page

        if not p_schadenumfang and "schadenumfang" in lower:
            p_schadenumfang = page

        if not p_wbw and "wiederbeschaffungswert geschätzt" in lower:
            p_wbw = page

    summary_lines = _get_lines(p_summary)
    invoice_lines = _get_lines(p_invoice)
    vehicle_lines = _get_lines(p_vehicle)

    base_lines = summary_lines or invoice_lines or _get_lines(full)

    # Aktenzeichen / Gutachtennummer
    data["AKTENZEICHEN"] = (
        _value_after_inline_label(invoice_lines, "Betreff Haftpflichtschaden -")
        or _next_line_after_exact_label(invoice_lines, "Gutachten - Nummer angeben!")
        or _value_after_inline_label(vehicle_lines, "Gutachten")
    )

    # Mandant
    raw_name = _value_after_inline_label(base_lines, "Anspruchsteller")
    anrede, clean_name = cleanup_name(raw_name)

    if not anrede:
        for line in invoice_lines:
            if clean_text(line).lower() == "herr":
                anrede = "Herr"
                break
            if clean_text(line).lower() == "frau":
                anrede = "Frau"
                break

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name

    mandant_addr = ""
    for i, line in enumerate(base_lines):
        if clean_text(line).lower().startswith("anspruchsteller "):
            if i + 1 < len(base_lines):
                mandant_addr = base_lines[i + 1]
            break

    mandant_strasse, mandant_plz_ort = _split_street_plz_ort(mandant_addr)
    data["MANDANT_STRASSE"] = mandant_strasse
    data["MANDANT_PLZ_ORT"] = mandant_plz_ort

    # Kennzeichen
    data["KENNZEICHEN_MANDANT"] = _value_after_inline_label(base_lines, "Amtliches Kennzeichen")
    data["KENNZEICHEN_GEGNER"] = _value_after_inline_label(base_lines, "Kennzeichen Unfallgegner")

    # Versicherung streng zeilenweise
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

    # Schadensnummer / Versicherungsscheinnummer
    data["SCHADENSNUMMER"] = _value_after_inline_label(base_lines, "Versicherungsscheinnummer")
    data["VERSICHERUNGSSCHEINNUMMER"] = data["SCHADENSNUMMER"]

    # Datum
    data["UNFALL_DATUM"] = _value_after_inline_label(base_lines, "Schadentag")
    data["BESICHTIGUNGSDATUM"] = _value_after_inline_label(base_lines, "Besichtigungsdatum")

    # Fahrzeugtyp
    data["FAHRZEUGTYP"] = _value_after_inline_label(vehicle_lines, "Typ / Untertyp")

    # Reparaturkosten / Wertminderung / WBW / Restwert
    data["REPARATURKOSTEN_NETTO"] = extract_money(
        p_summary + "\n" + full,
        [
            r"Reparaturkosten ohne MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Reparaturkosten netto\s*:\s*([0-9\.\,]+)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = extract_money(
        p_summary + "\n" + full,
        [
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
        ],
    )

    data["RESTWERT"] = extract_money(
        p_summary + "\n" + p_wbw + "\n" + full,
        [
            r"Restwert mit 19,00 % MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Restwert:\s*incl\.\s*MwSt\.\s*EUR\s*([0-9\.\,]+)",
        ],
    )

    # Gutachterkosten aus Rechnung
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

    # Standardschreiben Schnur: Reparatur netto
    data["VORSTEUERABZUG_RAW"] = ""

    # Schadenhergang + Schadenumfang
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

    data["SCHADENHERGANG"] = clean_text("\n".join(x for x in [hergang, schadenumfang] if x))

    # Defaults
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
