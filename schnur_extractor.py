from __future__ import annotations

import re
from typing import Dict, Any, List

from common import (
    search_first,
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

    # Wichtig: bei Schnur kommt oft "Straße 12, 12345 Ort"
    if "," in value:
        left, right = value.split(",", 1)
        return clean_text(left), clean_text(right)

    # Fallback: falls nur PLZ/Ort da ist
    if re.search(r"\b\d{5}\b", value):
        return "", value

    return value, ""


def _extract_first_money_after_label(text: str, label: str) -> str:
    if not text:
        return ""

    m = re.search(
        rf"{re.escape(label)}\s+EUR\s+([0-9\.\,]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        return extract_money(m.group(1), [r"([0-9\.\,]+)"])

    m = re.search(
        rf"{re.escape(label)}\s+([0-9\.\,]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        return extract_money(m.group(1), [r"([0-9\.\,]+)"])

    return ""


def parse_schnur(pages: List[str], pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data: Dict[str, Any] = {}

    p1 = ""
    p_summary = ""
    p_vehicle = ""
    p_unfall = ""
    p_invoice = ""

    for page in pages:
        lower = page.lower()

        if not p1 and "schaden-nr." in lower and "anspruchsteller" in lower:
            p1 = page

        if not p_summary and "zusammenfassung des gutachtens" in lower:
            p_summary = page

        if not p_vehicle and "technische daten und fahrzeugbeschreibung" in lower:
            p_vehicle = page

        if not p_unfall and "unfallhergang" in lower:
            p_unfall = page

        if not p_invoice and "rechnung" in lower and "rechnungsbetrag inkl. mwst" in lower:
            p_invoice = page

    base_page = p1 or full

    # ----------------------------
    # Aktenzeichen
    # ----------------------------
    data["AKTENZEICHEN"] = search_first(
        base_page,
        [
            r"Schaden-Nr\.\s*([A-Z0-9\-\/]+)",
            r"Gutachten-Nummer\s+([A-Z0-9\-\/]+)",
            r"Gutachten-Nr\.\s*([A-Z0-9\-\/]+)",
            r"(\b\d[A-Z0-9]{8,}\b)",
        ],
    )

    # ----------------------------
    # Anspruchsteller
    # ----------------------------
    anspruchsteller_block = _extract_block_between(
        base_page,
        "Anspruchsteller",
        "Schadentag",
    )

    if not anspruchsteller_block:
        anspruchsteller_block = _extract_block_between(
            base_page,
            "Anspruchsteller",
            "Besichtigungsdatum",
        )

    if not anspruchsteller_block:
        anspruchsteller_block = _extract_block_between(
            base_page,
            "Anspruchsteller",
            "Amtliches Kennzeichen",
        )

    lines = [clean_text(x) for x in anspruchsteller_block.split("\n") if clean_text(x)]

    raw_name = ""
    address_line = ""

    if len(lines) >= 3 and lines[0].lower() in {"frau", "herr"}:
        raw_name = f"{lines[0]} {lines[1]}"
        address_line = lines[2]
    elif len(lines) >= 2:
        raw_name = lines[0]
        address_line = lines[1]
    elif len(lines) >= 1:
        raw_name = lines[0]

    anrede, clean_name = cleanup_name(raw_name)

    if not anrede:
    if re.search(r"\bfrau\b", anspruchsteller_block, re.IGNORECASE):
        anrede = "Frau"
    elif re.search(r"\bherr\b", anspruchsteller_block, re.IGNORECASE):
        anrede = "Herr"
    else:
        first_name = clean_name.split()[0].strip().lower() if clean_name.strip() else ""
        if first_name in {"regina"}:
            anrede = "Frau"
    
    mandant_strasse, mandant_plz_ort = _split_street_plz_ort(address_line)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name
    data["MANDANT_STRASSE"] = mandant_strasse
    data["MANDANT_PLZ_ORT"] = mandant_plz_ort

    if not data["MANDANT_NAME"]:
        raw_name = search_first(base_page, [r"Anspruchsteller\s+(.+?)\n"])
        anrede, clean_name = cleanup_name(raw_name)
        data["MANDANT_ANREDE"] = anrede
        data["MANDANT_NAME"] = clean_name

    # ----------------------------
    # Kennzeichen
    # ----------------------------
    data["KENNZEICHEN_MANDANT"] = search_first(
        base_page,
        [
            r"Amtliches Kennzeichen\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,3}\s?\d{1,4})",
            r"Amtliches Kennzeichen\s+(.+?)\n",
        ],
    )

    data["KENNZEICHEN_GEGNER"] = search_first(
        base_page,
        [
            r"Kennzeichen Unfallgegner\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,3}\s?\d{1,4})",
            r"Kennzeichen Unfallgegner\s+(.+?)\n",
        ],
    )

    # ----------------------------
    # Versicherung
    # ----------------------------
    vers_block = _extract_block_between(
        base_page,
        "Versicherung",
        "Schaden- / Versicherungsscheinnummer",
    )

    vers_lines = [clean_text(x) for x in vers_block.split("\n") if clean_text(x)]

    vers_name = vers_lines[0] if len(vers_lines) >= 1 else ""
    vers_addr = vers_lines[1] if len(vers_lines) >= 2 else ""

    ver_strasse, ver_ort = _split_street_plz_ort(vers_addr)

    data["VERSICHERUNG"] = vers_name
    data["VER_STRASSE"] = ver_strasse
    data["VER_ORT"] = ver_ort

    if not data["VERSICHERUNG"]:
        data["VERSICHERUNG"] = search_first(
            base_page,
            [
                r"Versicherung\s+(.+?)\n",
            ],
        )

    # ----------------------------
    # Schadensnummer
    # ----------------------------
    schaden_combo = search_first(
        base_page,
        [
            r"Schaden-\s*/\s*Versicherungsscheinnummer\s+(.+?)\n",
            r"Schaden-Nr\.\s+(.+?)\n",
        ],
    )

    if " / " in schaden_combo:
        left, right = schaden_combo.split(" / ", 1)
        data["SCHADENSNUMMER"] = clean_text(left)
        data["VERSICHERUNGSSCHEINNUMMER"] = clean_text(right)
    else:
        data["SCHADENSNUMMER"] = clean_text(schaden_combo)
        data["VERSICHERUNGSSCHEINNUMMER"] = ""

    # ----------------------------
    # Datum
    # ----------------------------
    data["UNFALL_DATUM"] = search_first(
        base_page,
        [
            r"Schadentag\s+(\d{2}\.\d{2}\.\d{4})",
            r"Unfalldatum\s+(\d{2}\.\d{2}\.\d{4})",
            r"Unfalltag\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    data["BESICHTIGUNGSDATUM"] = search_first(
        base_page,
        [
            r"Besichtigungsdatum\s+(\d{2}\.\d{2}\.\d{4})",
            r"Besichtigung(?: am)?\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    # ----------------------------
    # Fahrzeugtyp
    # ----------------------------
    data["FAHRZEUGTYP"] = search_first(
        p_vehicle or full,
        [
            r"Typ\s*/\s*Untertyp\s+(.+?)\n",
        ],
    )

    if not data["FAHRZEUGTYP"]:
        fahrzeug1 = search_first(
            p_vehicle or full,
            [
                r"Fahrzeug\s+(.+?)\n",
                r"Fahrzeugart\s+(.+?)\n",
            ],
        )
        fahrzeug2 = search_first(
            p_vehicle or full,
            [
                r"Typ\s+(.+?)\n",
            ],
        )
        data["FAHRZEUGTYP"] = clean_text(" ".join(x for x in [fahrzeug1, fahrzeug2] if x))

    # ----------------------------
    # Reparaturkosten / Wertminderung / WBW / Restwert
    # ----------------------------
    data["REPARATURKOSTEN_NETTO"] = extract_money(
        p_summary or full,
        [
            r"Reparaturkosten ohne MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Reparaturkosten ohne MwSt\.\s*([0-9\.\, ]+)",
            r"Reparaturkosten netto\s*([0-9\.\, ]+)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = extract_money(
        p_summary or full,
        [
            r"Reparaturkosten mit 19,00\s*%\s*MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Reparaturkosten brutto\s*([0-9\.\, ]+)",
        ],
    )

    data["WERTMINDERUNG"] = extract_money(
        p_summary or full,
        [
            r"Wertminderung\s+EUR\s+([0-9\.\,]+)",
            r"Wertminderung\s*([0-9\.\, ]+)",
        ],
    )

    data["WBW"] = extract_money(
        p_summary or full,
        [
            r"Wiederbeschaffungswert.*?\s+EUR\s+([0-9\.\,]+)",
            r"Wiederbeschaffungswert\s*([0-9\.\, ]+)",
        ],
    )

    data["RESTWERT"] = extract_money(
        p_summary or full,
        [
            r"Restwert\s+EUR\s+([0-9\.\,]+)",
            r"Restwert\s*([0-9\.\, ]+)",
        ],
    )

    # ----------------------------
    # Gutachterkosten aus Rechnung
    # ----------------------------
    data["GUTACHTERKOSTEN_NETTO"] = extract_money(
        p_invoice or full,
        [
            r"Rechnungsbetrag inkl\.\s*MwSt\s+EUR\s+([0-9\.\,]+)",
            r"Rechnungsbetrag inkl\.\s*MwSt\s*([0-9\.\, ]+)",
        ],
    )

    data["GUTACHTERKOSTEN_BRUTTO"] = extract_money(
        p_invoice or full,
        [
            r"Rechnungsbetrag inkl\.\s*MwSt\.\s+EUR\s+([0-9\.\,]+)",
            r"Rechnungsbetrag inkl\.\s*MwSt\.\s*([0-9\.\, ]+)",
        ],
    )

    # Für Reparaturkosten immer netto erzwingen
    data["VORSTEUERABZUG_RAW"] = "Ja"

    # ----------------------------
    # Schadenhergang
    # ----------------------------
    hergang = search_first(
        p_unfall or full,
        [
            r"Unfallhergang\s+(.+)",
        ],
    )
    data["SCHADENHERGANG"] = clean_text(hergang)

    # ----------------------------
    # Defaults
    # ----------------------------
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
