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
            return clean_text(line_clean[len(label):].strip(" :"))
    return ""


def _next_line_after_exact_label(lines: List[str], label: str) -> str:
    label_norm = clean_text(label).lower()
    for i, line in enumerate(lines):
        if clean_text(line).lower() == label_norm and i + 1 < len(lines):
            return lines[i + 1]
    return ""


def _find_name_block_in_lines(lines: List[str], clean_name: str) -> tuple[str, str, str]:
    """
    Sucht im Briefkopf:
    Herr/Frau
    Vorname Nachname
    Straße
    PLZ Ort
    """
    if not clean_name:
        return "", "", ""

    name_norm = clean_text(clean_name).lower()

    for i, line in enumerate(lines):
        line_norm = clean_text(line).lower()

        # Fall 1: eigene Zeile mit Name, Zeile davor ist Herr/Frau
        if line_norm == name_norm:
            anrede = ""
            if i - 1 >= 0:
                prev_line = clean_text(lines[i - 1]).lower()
                if prev_line == "herr":
                    anrede = "Herr"
                elif prev_line == "frau":
                    anrede = "Frau"

            street = clean_text(lines[i + 1]) if i + 1 < len(lines) else ""
            city = clean_text(lines[i + 2]) if i + 2 < len(lines) else ""

            if anrede:
                return anrede, street, city

        # Fall 2: gleiche Zeile "Herr Steffen Altwein"
        if line_norm == f"herr {name_norm}":
            street = clean_text(lines[i + 1]) if i + 1 < len(lines) else ""
            city = clean_text(lines[i + 2]) if i + 2 < len(lines) else ""
            return "Herr", street, city

        if line_norm == f"frau {name_norm}":
            street = clean_text(lines[i + 1]) if i + 1 < len(lines) else ""
            city = clean_text(lines[i + 2]) if i + 2 < len(lines) else ""
            return "Frau", street, city

    return "", "", ""


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
    all_lines = _get_lines(full)

    base_lines = summary_lines or invoice_lines or all_lines

    # Aktenzeichen / Gutachtennummer
    aktenzeichen = (
        _value_after_inline_label(invoice_lines, "Betreff Haftpflichtschaden -")
        or _next_line_after_exact_label(invoice_lines, "Gutachten - Nummer angeben!")
    )

    if aktenzeichen:
        m = re.search(r"\b(5[A-Z0-9]+)\b", aktenzeichen)
        data["AKTENZEICHEN"] = m.group(1) if m else clean_text(aktenzeichen)
    else:
        m = re.search(r"\b(5[A-Z0-9]+)\b", p_vehicle or "")
        data["AKTENZEICHEN"] = m.group(1) if m else ""

    # Mandant
    raw_name = _value_after_inline_label(base_lines, "Anspruchsteller")
    _, clean_name = cleanup_name(raw_name)

    anrede = ""
    mandant_strasse = ""
    mandant_plz_ort = ""

    # 1) Erst Briefkopf Rechnung
    if p_invoice:
        anrede, mandant_strasse, mandant_plz_ort = _find_name_block_in_lines(invoice_lines, clean_name)

    # 2) Dann Briefkopf anderer Seiten
    if not anrede:
        for lines in (summary_lines, all_lines):
            anrede2, street2, city2 = _find_name_block_in_lines(lines, clean_name)
            if anrede2:
                anrede = anrede2
                if not mandant_strasse:
                    mandant_strasse = street2
                if not mandant_plz_ort:
                    mandant_plz_ort = city2
                break

    # 3) Fallback Adresse aus Anspruchstellerzeile der Zusammenfassung
    if not mandant_strasse or not mandant_plz_ort:
        mandant_addr = ""
        for i, line in enumerate(base_lines):
            if clean_text(line).lower().startswith("anspruchsteller "):
                if i + 1 < len(base_lines):
                    mandant_addr = base_lines[i + 1]
                break

        m_strasse, m_plz_ort = _split_street_plz_ort(mandant_addr)

        if not mandant_strasse:
            mandant_strasse = m_strasse
        if not mandant_plz_ort:
            mandant_plz_ort = m_plz_ort

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name
    data["MANDANT_STRASSE"] = mandant_strasse
    data["MANDANT_PLZ_ORT"] = mandant_plz_ort

    # Kennzeichen
    data["KENNZEICHEN_MANDANT"] = _value_after_inline_label(base_lines, "Amtliches Kennzeichen")
    data["KENNZEICHEN_GEGNER"] = _value_after_inline_label(base_lines, "Kennzeichen Unfallgegner")

    # Versicherung
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

    # Schnur Standardschreiben Reparaturschaden
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

    data["SCHADENHERGANG"] = clean_text("\n".join(x for x in [hergang, schadenumfang] if x]))

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
