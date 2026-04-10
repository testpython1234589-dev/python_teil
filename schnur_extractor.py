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

    if "," in value:
        left, right = value.split(",", 1)
        return clean_text(left), clean_text(right)

    if re.search(r"\b\d{5}\b", value):
        return "", value

    return value, ""


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

    base_page = p_summary or p_invoice or full

    # Gutachtennummer / Aktenzeichen
    data["AKTENZEICHEN"] = search_first(
        p_summary + "\n" + p_vehicle + "\n" + full,
        [
            r"Gutachten[\s\-]+Nummer.*?\n(5[A-Z0-9]+)",
            r"Betreff\s+Haftpflichtschaden\s*-\s*(5[A-Z0-9]+)",
            r"Gutachten\s+(5[A-Z0-9]+)\s+Datum",
        ],
    )

    # Mandant
    raw_name = search_first(
        base_page,
        [
            r"Anspruchsteller\s+(.+?)\n",
        ],
    )
    anrede, clean_name = cleanup_name(raw_name)

    if not anrede:
        if re.search(r"\bHerr\b", p_invoice, re.IGNORECASE):
            anrede = "Herr"
        elif re.search(r"\bFrau\b", p_invoice, re.IGNORECASE):
            anrede = "Frau"

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name

    mandant_addr = search_first(
        base_page,
        [
            r"Anspruchsteller\s+.+?\n(.+)",
        ],
    )
    mandant_strasse, mandant_plz_ort = _split_street_plz_ort(mandant_addr)
    data["MANDANT_STRASSE"] = mandant_strasse
    data["MANDANT_PLZ_ORT"] = mandant_plz_ort

    # Kennzeichen
    data["KENNZEICHEN_MANDANT"] = search_first(
        base_page,
        [
            r"Amtliches Kennzeichen\s+(.+?)\n",
        ],
    )

    data["KENNZEICHEN_GEGNER"] = search_first(
        base_page,
        [
            r"Kennzeichen Unfallgegner\s+(.+?)\n",
        ],
    )

    # Versicherung
    data["VERSICHERUNG"] = search_first(
        base_page,
        [
            r"Versicherung\s+(.+?)\n",
        ],
    )

    vers_addr = search_first(
        base_page,
        [
            r"Versicherung\s+.+?\n(.+)",
        ],
    )
    ver_strasse, ver_ort = _split_street_plz_ort(vers_addr)
    data["VER_STRASSE"] = ver_strasse
    data["VER_ORT"] = ver_ort

    # Schadensnummer / Versicherungsscheinnummer
    data["SCHADENSNUMMER"] = search_first(
        base_page,
        [
            r"Versicherungsscheinnummer\s+(.+?)\n",
        ],
    )
    data["VERSICHERUNGSSCHEINNUMMER"] = data["SCHADENSNUMMER"]

    # Datum
    data["UNFALL_DATUM"] = search_first(
        base_page,
        [
            r"Schadentag\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    data["BESICHTIGUNGSDATUM"] = search_first(
        base_page,
        [
            r"Besichtigungsdatum\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    # Fahrzeugtyp
    data["FAHRZEUGTYP"] = search_first(
        p_vehicle or full,
        [
            r"Typ\s*/\s*Untertyp\s+(.+?)\n",
        ],
    )

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

    # Schnur: Standardschreiben Reparaturschaden -> Reparatur netto
    data["VORSTEUERABZUG_RAW"] = ""

    # Schadenhergang + Schadenumfang
    hergang = search_first(
        p_unfall or full,
        [
            r"Unfallhergang:\s+(.+?)\nBlatt",
            r"Unfallhergang\s+(.+?)\nBlatt",
        ],
    )

    schadenumfang = search_first(
        p_schadenumfang or full,
        [
            r"Schadenumfang:\s+(.+?)\nBemerkung",
            r"Schadenumfang\s+(.+?)\nBemerkung",
        ],
    )

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
