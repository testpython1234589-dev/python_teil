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
        r"Anspruchsteller.*?Name\s*\n(.+?)\n(Herr|Frau)\s+(.+?)\n",
        full,
        re.S | re.I,
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

    adr = re.search(
        r"Anspruchsteller.*?"
        r"Straße\s*\n(.+?)\n"
        r"PLZ\s*Ort\s*\n(.+?)\n",
        full,
        re.S | re.I,
    )

    if adr:
        data["MANDANT_STRASSE"] = adr.group(1).strip()
        data["MANDANT_PLZ_ORT"] = adr.group(2).strip()

    # ===================================================
    # UNFALL
    # ===================================================

    data["UNFALL_DATUM"] = _search(
        r"Unfall.*?Datum\s*\n([0-9\.]{10})",
        full,
    )

    data["UNFALL_ORT"] = _search(
        r"Unfall.*?Ort\s*\n(.+?)\n",
        full,
    )

    # ===================================================
    # VERSICHERUNG
    # ===================================================

    vers = re.search(
        r"Versicherung.*?"
        r"Name\s*\n(.+?)\n"
        r"Straße\s*\n(.+?)\n"
        r"PLZ\s*Ort\s*\n(.+?)\n",
        full,
        re.S | re.I,
    )

    if vers:
        data["VERSICHERUNG"] = vers.group(1).strip()
        data["VER_STRASSE"] = vers.group(2).strip()
        data["VER_ORT"] = vers.group(3).strip()

    data["SCHADENSNUMMER"] = _search(
        r"Schadennummer\s*\n(.+?)\n",
        full,
    )

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

    data["KENNZEICHEN"] = data.get(
        "KENNZEICHEN_MANDANT",
        "",
    )

    data["KENNZEICHEN_GEGNER"] = _search(
        r"Unfallgegner.*?Kennzeichen\s*\n(.+?)\n",
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

    data["REPARATURKOSTEN_NETTO"] = gx._extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.\s*([0-9\., ]+€?)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = gx._extract_money(
        full,
        [
            r"Schadenhöhe inkl\. MwSt\.\s*([0-9\., ]+€?)",
        ],
    )

    data["WBW"] = gx._extract_money(
        full,
        [
            r"Wiederbeschaffungswert.*?([0-9\., ]+€)",
        ],
    )

    data["RESTWERT"] = gx._extract_money(
        full,
        [
            r"Restwert.*?([0-9\., ]+€)",
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
