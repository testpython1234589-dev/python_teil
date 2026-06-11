from __future__ import annotations

from typing import Dict, Any
import re

import gutachten_extractor as gx


def _search(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.S | re.I)
    return m.group(1).strip() if m else ""


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:

    full = "\n".join(pages)
    seite4 = pages[3] if len(pages) >= 4 else full
    seite5 = pages[4] if len(pages) >= 5 else full
    seite8 = pages[7] if len(pages) >= 8 else full

    data: Dict[str, Any] = {}
    data["_PARSER"] = "nfz_totalschaden"

    # ===================================================
    # AKTENZEICHEN
    # ===================================================

    data["AKTENZEICHEN"] = _search(
        r"Aktenzeichen\s*\n([A-Z0-9\-\/]+)",
        full,
    )

    # ===================================================
    # ANSPRUCHSTELLER (Firma + Geschäftsführer)
    # ===================================================

    
    m = re.search(
    r"Anspruchsteller\s+Name\s+(.+?)\n(Herr|Frau)\s+(.+?)\n",
    full,
    re.S,
    )

    if m:
        firma = m.group(1).strip()
        anrede = m.group(2).strip()
        person = m.group(3).strip()

        data["MANDANT_ANREDE"] = anrede

        # Geschäftsführerlogik
        data["MANDANT_VORNAME"] = person
        data["MANDANT_NACHNAME"] = firma
        data["MANDANT_NAME"] = firma
        data["MANDANT_FIRMA"] = firma

        data["MANDANT_VOLLNAME"] = (
            f"{person} Geschäftsführer von {firma}"
        )

    # ===================================================
    # ADRESSE ANSPRUCHSTELLER (Seite 5)
    # ===================================================

    m = re.search(
    r"Anspruchsteller.*?"
    r"Straße\s+(.+?)\n"
    r"PLZ Ort\s+(.+?)\n",
    full,
    re.S,
    )

    if m:
        data["MANDANT_STRASSE"] = m.group(1).strip()
        data["MANDANT_PLZ_ORT"] = m.group(2).strip()
    # ===================================================
    # UNFALL
    # ===================================================

    data["UNFALL_DATUM"] = _search(
        r"Unfall\s+Datum\s*[: ]+\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
        full,
    )

    data["UNFALL_ORT"] = _search(
        r"Ort\s+([^\n]+)",
        full,
    )

    # ===================================================
    # VERSICHERUNG
    # ===================================================

    vers = re.search(
        r"Versicherung.*?"
        r"Name\s+(.+?)\n"
        r"Straße\s+(.+?)\n"
        r"PLZ\s+Ort\s+(.+?)\n"
        r"Schadennummer\s+(.+?)\n",
        seite5,
        re.S | re.I,
    )
    
    if vers:
        data["VERSICHERUNG"] = vers.group(1).strip()
        data["VER_STRASSE"] = vers.group(2).strip()
        data["VER_ORT"] = vers.group(3).strip()
        data["SCHADENSNUMMER"] = " ".join(vers.group(4).split())

    

    # ===================================================
    # FAHRZEUG
    # ===================================================

    data["FAHRZEUGTYP"] = _search(
        r"Hersteller\s*Modell\s*\n(.+?)\n",
        full,
    )

    data["KENNZEICHEN_MANDANT"] = _search(
        r"Eigenes\s+Kennzeichen\s*\n(.+?)\n",
        full,
    )

    data["KENNZEICHEN"] =_search(
        r"(?:Amtliches Kennzeichen|Kennzeichen)\s+([A-ZÄÖÜ\- ]+\d+)",
        full,
    )

    data["KENNZEICHEN_GEGNER"] = _search(
        r"Unfallgegner.*?Kennzeichen\s+([A-ZÄÖÜ\- ]+\d+)",
        full,
    )

    # ===================================================
    # VORSTEUER
    # ===================================================

    data["VORSTEUERABZUG_RAW"] = _search(
        r"Vorsteuerabzug.*?(Ja|Nein)",
        full,
    )

    if data["VORSTEUERABZUG_RAW"].lower() == "ja":
        data["VORSTEUERBERECHTIGUNG"] = (
            "vorsteuerabzugsberechtigt"
        )
    elif data["VORSTEUERABZUG_RAW"].lower() == "nein":
        data["VORSTEUERBERECHTIGUNG"] = (
            "nicht vorsteuerabzugsberechtigt"
        )

    # ===================================================
    # FAHRZEUGWERT (Seite 4)
    # ===================================================


    data["WBW"] = gx._extract_money(
    seite4,
    [
        r"Wiederbeschaffungswert.*?([0-9]+\.[0-9]{3},[0-9]{2}\s*€)"
    ],
    )
    
    data["RESTWERT"] = gx._extract_money(
        full,
        [
           r"Restwert.*?([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€)",
        ],
    )

    # ===================================================
    # SONDERKOSTEN
    # ===================================================

    data["MELDUNGSKOSTEN"] = gx._extract_money(
        full,
        [
            r"Ab-\s*&\s*Anmeldegebühren\s*([0-9\., ]+€?)",
        ],
    )

    # ===================================================
    # GUTACHTERKOSTEN
    # ===================================================

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

    # ===================================================
    # SCHADENHERGANG
    # ===================================================

    data["SCHADENHERGANG"] = _search(
        r"Nach Angaben des Anspruchstellers(.*?)(?:\n\n|\Z)",
        full,
    )

    return data
