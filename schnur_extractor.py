from __future__ import annotations

from typing import Dict, Any, List

from common import (
    search_first,
    find_page,
    extract_money,
    cleanup_name,
    split_street_place,
    clean_text,
)


def parse_schnur(pages: List[str], pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data: Dict[str, Any] = {}

    # Wichtige Seiten
    p1 = ""
    for page in pages:
        if "Schaden-Nr." in page and "Anspruchsteller" in page:
            p1 = page
            break

    p4 = ""
    for page in pages:
        if "Unfallhergang" in page:
            p4 = page
            break

    p5 = ""
    for page in pages:
        if "Schadenumfang" in page or "Achsvermessung" in page:
            p5 = page
            break

    p10 = ""
    for page in pages:
        if "Reparaturkosten" in page and "brutto" in page.lower():
            p10 = page
            break

    p11 = ""
    for page in pages:
        if "Wiederbeschaffungswert" in page and "Wertminderung" in page:
            p11 = page
            break

    # Gutachtennummer / Aktenzeichen
    data["AKTENZEICHEN"] = search_first(
        p1 or full,
        [
            r"Schaden-Nr\.\s*([A-Z0-9\-\/]+)",
            r"Gutachten-Nr\.\s*([A-Z0-9\-\/]+)",
            r"(\b\d[A-Z0-9]{8,}\b)",
        ],
    )

    # Mandant
    raw_name = search_first(
        p1 or full,
        [
            r"Anspruchsteller\s+(.+?)\n",
        ],
    )
    anrede, clean_name = cleanup_name(raw_name)
    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name

    data["MANDANT_STRASSE"] = search_first(
        p1 or full,
        [
            r"Anspruchsteller\s+.+?\n(.+?)\n\d{5}\s+.+",
        ],
    )
    data["MANDANT_PLZ_ORT"] = search_first(
        p1 or full,
        [
            r"Anspruchsteller\s+.+?\n.+?\n(\d{5}\s+.+?)\n",
        ],
    )

    # Kennzeichen eigenes Fahrzeug
    data["KENNZEICHEN_MANDANT"] = search_first(
        p1 or full,
        [
            r"Amtliches Kennzeichen\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,3}\s?\d{1,4})",
            r"Kennzeichen\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,3}\s?\d{1,4})",
        ],
    )

    # Gegnerkennzeichen
    data["KENNZEICHEN_GEGNER"] = search_first(
        p1 or full,
        [
            r"Kennzeichen Unfallgegner\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,3}\s?\d{1,4})",
            r"Unfallgegner\s+.+?\n.+?\n([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,3}\s?\d{1,4})",
        ],
    )

    # Versicherung
    data["VERSICHERUNG"] = search_first(
        p1 or full,
        [
            r"Versicherung\s+(.+?)\n",
        ],
    )
    data["VER_STRASSE"] = search_first(
        p1 or full,
        [
            r"Versicherung\s+.+?\n(.+?)\n\d{5}\s+.+",
        ],
    )
    data["VER_ORT"] = search_first(
        p1 or full,
        [
            r"Versicherung\s+.+?\n.+?\n(\d{5}\s+.+?)\n",
        ],
    )

    # Schadensnummer getrennt von Versicherungsscheinnummer
    schaden_combo = search_first(
        p1 or full,
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

    # Unfall- / Besichtigungsdatum
    data["UNFALL_DATUM"] = search_first(
        p1 or full,
        [
            r"Schadentag\s+(\d{2}\.\d{2}\.\d{4})",
            r"Unfalltag\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )
    data["BESICHTIGUNGSDATUM"] = search_first(
        p1 or full,
        [
            r"Besichtigung am\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    # Fahrzeugtyp
    fahrzeug1 = search_first(
        p1 or full,
        [
            r"Fahrzeug\s+(.+?)\n",
            r"Fahrzeugart\s+(.+?)\n",
        ],
    )
    fahrzeug2 = search_first(
        p1 or full,
        [
            r"Typ\s+(.+?)\n",
        ],
    )
    data["FAHRZEUGTYP"] = clean_text(" ".join(x for x in [fahrzeug1, fahrzeug2] if x))

    # Reparaturkosten
    data["REPARATURKOSTEN_NETTO"] = extract_money(
        p10 or p1 or full,
        [
            r"Reparaturkosten netto\s*([0-9\., ]+)",
            r"Reparaturkosten\s*netto\s*([0-9\., ]+)",
        ],
    )
    data["REPARATURKOSTEN_BRUTTO"] = extract_money(
        p10 or p1 or full,
        [
            r"Reparaturkosten brutto\s*([0-9\., ]+)",
            r"Reparaturkosten\s*brutto\s*([0-9\., ]+)",
        ],
    )

    # WBW / Wertminderung / Restwert
    data["WBW"] = extract_money(
        p11 or p1 or full,
        [
            r"Wiederbeschaffungswert\s*([0-9\., ]+)",
        ],
    )
    data["WERTMINDERUNG"] = extract_money(
        p11 or p1 or full,
        [
            r"Wertminderung\s*([0-9\., ]+)",
        ],
    )
    data["RESTWERT"] = extract_money(
        p11 or full,
        [
            r"Restwert\s*([0-9\., ]+)",
        ],
    )

    # Wertverbesserung bei Schnur oft leer
    data["WERTVERBESSERUNG"] = extract_money(
        full,
        [
            r"Wertverbesserung\s*([0-9\., ]+)",
        ],
    )

    # Schadenhergang
    hergang = search_first(
        p4 or full,
        [
            r"Unfallhergang\s+(.+)",
        ],
    )
    schadenumfang = search_first(
        p5 or full,
        [
            r"Schadenumfang\s+(.+)",
        ],
    )
    data["SCHADENHERGANG"] = clean_text("\n".join(x for x in [hergang, schadenumfang] if x))

    # Diese Felder im Beispiel nicht sicher vorhanden
    data.setdefault("UNFALL_UHRZEIT", "")
    data.setdefault("UNFALL_STRASSE", "")
    data.setdefault("UNFALL_ORT", "")
    data.setdefault("GUTACHTERKOSTEN_NETTO", "")
    data.setdefault("GUTACHTERKOSTEN_BRUTTO", "")
    data.setdefault("MELDUNGSKOSTEN_RAW", "")
    data.setdefault("ZUSATZKOSTEN1_NAME", "")
    data.setdefault("ZUSATZKOSTEN1_BETRAG", "")
    data.setdefault("ZUSATZKOSTEN2_NAME", "")
    data.setdefault("ZUSATZKOSTEN2_BETRAG", "")
    data.setdefault("ZUSATZKOSTEN3_NAME", "")
    data.setdefault("ZUSATZKOSTEN3_BETRAG", "")

    data["_PARSER"] = "schnur"
    return data
