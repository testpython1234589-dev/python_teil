from __future__ import annotations

import re
from typing import Dict, Any, List

from common import (
    search_first,
    clean_text,
    cleanup_name,
    extract_money,
)


def _line_value(page: str, label: str) -> str:
    """
    Holt den Wert hinter einem Label in einer Tabellen-/Zeilenstruktur.
    Beispiel:
    'Kennzeichen Unfallgegner    SLK PP47'
    """
    if not page:
        return ""

    pat = rf"{re.escape(label)}\s+(.+)"
    m = re.search(pat, page, re.IGNORECASE)
    if m:
        return clean_text(m.group(1))
    return ""


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


def parse_schnur(pages: List[str], pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data: Dict[str, Any] = {}

    # ----------------------------
    # Seiten sauber identifizieren
    # ----------------------------
    p1 = ""
    p_summary = ""
    p_vehicle = ""
    p_unfall = ""

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

    base_page = p1 or full

    # ----------------------------
    # AKTENZEICHEN / GUTACHTEN-NR.
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
    # Mandant / Anspruchsteller
    # ----------------------------
    # Block zwischen Anspruchsteller und nächstem Feld
    anspruchsteller_block = _extract_block_between(
        base_page,
        "Anspruchsteller",
        "Amtliches Kennzeichen",
    )

    if not anspruchsteller_block:
        anspruchsteller_block = _extract_block_between(
            base_page,
            "Anspruchsteller",
            "Kennzeichen Unfallgegner",
        )

    block_lines = [clean_text(x) for x in anspruchsteller_block.split("\n") if clean_text(x)]

    raw_name = block_lines[0] if len(block_lines) >= 1 else ""
    anrede, clean_name = cleanup_name(raw_name)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name
    data["MANDANT_STRASSE"] = block_lines[1] if len(block_lines) >= 2 else ""
    data["MANDANT_PLZ_ORT"] = block_lines[2] if len(block_lines) >= 3 else ""

    # Fallbacks
    if not data["MANDANT_NAME"]:
        raw_name = search_first(
            base_page,
            [
                r"Anspruchsteller\s+(.+?)\n",
            ],
        )
        anrede, clean_name = cleanup_name(raw_name)
        data["MANDANT_ANREDE"] = anrede
        data["MANDANT_NAME"] = clean_name

    if not data["MANDANT_STRASSE"]:
        data["MANDANT_STRASSE"] = search_first(
            base_page,
            [
                r"Anspruchsteller\s+.+?\n(.+?)\n\d{5}\s+.+",
            ],
        )

    if not data["MANDANT_PLZ_ORT"]:
        data["MANDANT_PLZ_ORT"] = search_first(
            base_page,
            [
                r"Anspruchsteller\s+.+?\n.+?\n(\d{5}\s+.+?)\n",
            ],
        )

    # ----------------------------
    # Kennzeichen eigenes Fahrzeug
    # ----------------------------
    data["KENNZEICHEN_MANDANT"] = search_first(
        base_page,
        [
            r"Amtliches Kennzeichen\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,3}\s?\d{1,4})",
            r"Amtliches Kennzeichen\s+(.+?)\n",
        ],
    )

    # ----------------------------
    # Kennzeichen Gegner
    # ----------------------------
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
    data["VERSICHERUNG"] = vers_lines[0] if len(vers_lines) >= 1 else ""
    data["VER_STRASSE"] = vers_lines[1] if len(vers_lines) >= 2 else ""
    data["VER_ORT"] = vers_lines[2] if len(vers_lines) >= 3 else ""

    if not data["VERSICHERUNG"]:
        data["VERSICHERUNG"] = search_first(
            base_page,
            [
                r"Versicherung\s+(.+?)\n",
            ],
        )

    # ----------------------------
    # Schadensnummer
    # Beispiel:
    # DG2026-20012516 / DG-200936109
    # -> links = Schadensnummer
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

    # Extra-Schutz: nur typische Schadensnummer rausziehen
    if data["SCHADENSNUMMER"]:
        m = re.search(r"[A-Z]{1,4}\d{2,}[-/A-Z0-9]*", data["SCHADENSNUMMER"])
        if m:
            data["SCHADENSNUMMER"] = clean_text(m.group(0))

    # ----------------------------
    # Datum
    # ----------------------------
    data["UNFALL_DATUM"] = search_first(
        base_page,
        [
            r"Schadentag\s+(\d{2}\.\d{2}\.\d{4})",
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
    # Beispiel:
    # Typ / Untertyp    Duster I / Destination 4x2
    # ----------------------------
    data["FAHRZEUGTYP"] = search_first(
        p_vehicle or full,
        [
            r"Typ\s*/\s*Untertyp\s+(.+?)\n",
            r"Fahrzeugart\s+(.+?)\n",
            r"Fahrzeug\s+(.+?)\n",
        ],
    )

    # Fallback: Fahrzeug + Typ kombinieren
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
    # Reparaturkosten / Wertminderung
    # Seite "Zusammenfassung des Gutachtens"
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
            r"Reparaturkosten MwSt\.\s*([0-9\.\, ]+)",
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
    # Defaults für restliche Felder
    # ----------------------------
    data.setdefault("UNFALL_UHRZEIT", "")
    data.setdefault("UNFALL_STRASSE", "")
    data.setdefault("UNFALL_ORT", "")
    data.setdefault("GUTACHTERKOSTEN_NETTO", "")
    data.setdefault("GUTACHTERKOSTEN_BRUTTO", "")
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
