from __future__ import annotations

from typing import Dict, Any
import re

import gutachten_extractor as gx


def _search(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.S | re.I)
    return m.group(1).strip() if m else ""


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:

    full = "\n".join(pages)

    data: Dict[str, Any] = {}

    data["_PARSER"] = "nfz_totalschaden"

    # ---------------------------------------------------
    # AKTENZEICHEN
    # ---------------------------------------------------

    data["AKTENZEICHEN"] = _search(
        r"Aktenzeichen\s*\n([A-Z0-9\-\/]+)",
        full,
    )

    # ---------------------------------------------------
    # Anspruchsteller
    # ---------------------------------------------------
    
     m = re.search(
        r"Anspruchsteller\s*\n(.+?)\n(Herr|Frau)\s+(.+?)\n",
        full,
        re.S,
     )
    
    if m:
        firma = m.group(1).strip()
        anrede = m.group(2).strip()
        person = m.group(3).strip()
    
        data["MANDANT_FIRMA"] = firma
        data["MANDANT_ANREDE"] = anrede
        data["MANDANT_VOLLNAME"] = person
    
        teile = person.split()
    
        if teile:
            data["MANDANT_VORNAME"] = teile[0]
            data["MANDANT_NACHNAME"] = " ".join(teile[1:])
    # ---------------------------------------------------
    # Unfall
    # ---------------------------------------------------

    data["UNFALL_DATUM"] = _search(
        r"Unfall Datum\s*\n([0-9\.]+)",
        full,
    )

    data["UNFALL_ORT"] = _search(
        r"Ort\s*\n(.+?)\nUnfallgegner",
        full,
    )

    # ---------------------------------------------------
    # Gegner
    # ---------------------------------------------------

    data["KENNZEICHEN_GEGNER"] = _search(
        r"Kennzeichen\s*\n([A-ZÄÖÜ0-9\-\s]+)",
        full,
    )

    # ---------------------------------------------------
    # Versicherung
    # ---------------------------------------------------

    data["VERSICHERUNG"] = _search(
        r"Versicherung\s*\n(.+?)\n",
        full,
    )

    data["SCHADENSNUMMER"] = _search(
        r"Schadennummer\s*\n(.+?)\n",
        full,
    )

    # ---------------------------------------------------
    # Fahrzeug
    # ---------------------------------------------------

    data["FAHRZEUGTYP"] = _search(
        r"Hersteller Modell\s*\n(.+?)\n",
        full,
    )

    data["KENNZEICHEN_MANDANT"] = _search(
        r"Kennzeichen\s*\n([A-Z]{1,4}[:\s]+[A-Z]{1,3}\s+\d+)",
        full,
    )

    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    # ---------------------------------------------------
    # Vorsteuer
    # ---------------------------------------------------

    data["VORSTEUERABZUG_RAW"] = _search(
        r"Vorsteuerabzug\s*[\n\s]+(Ja|Nein)",
        full,
    )

    # ---------------------------------------------------
    # Werte Totalschaden
    # ---------------------------------------------------

    data["REPARATURKOSTEN_NETTO"] = gx._extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.[\s\n]*([0-9\., ]+€?)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = gx._extract_money(
        full,
        [
            r"Schadenhöhe inkl\. MwSt\.[\s\n]*([0-9\., ]+€?)",
        ],
    )

    data["WBW"] = gx._extract_money(
        full,
        [
            r"Wiederbeschaffungswert.*?\)\s*([0-9\., ]+€?)",
        ],
    )

    data["RESTWERT"] = gx._extract_money(
        full,
        [
            r"Restwert:\s*([\d\.]+,\d{2}\s*€)",
        ],
    )

    data["MELDUNGSKOSTEN"] = gx._extract_money(
        full,
        [
            r"Ab- & Anmeldegebühren\s*([0-9\., ]+€?)",
        ],
    )

    # ---------------------------------------------------
    # Gutachterkosten
    # ---------------------------------------------------

    data["GUTACHTERKOSTEN_NETTO"] = gx._extract_money(
        full,
        [
            r"Gesamtbetrag ohne MwSt\.\s*([0-9\., ]+€?)",
        ],
    )

    data["GUTACHTERKOSTEN_BRUTTO"] = gx._extract_money(
        full,
        [
            r"Gesamtbetrag inkl\. MwSt\.\s*([0-9\., ]+€?)",
        ],
    )

    # ---------------------------------------------------
    # Schadenhergang
    # ---------------------------------------------------

    data["SCHADENHERGANG"] = _search(
        r"Nach Angaben.*?(?=\n\n)",
        full,
    )

    return data
