from __future__ import annotations

from typing import Dict, Any
import re

import gutachten_extractor as gx


def _search(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.S | re.I)
    return m.group(1).strip() if m else ""


def _one_line(value: str) -> str:
    return " ".join((value or "").split())


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
    # ALT war zu allgemein und hat "MER" erwischt.
    # NEU sucht gezielt nach NFZ-202606-251 usw.

    data["AKTENZEICHEN"] = _search(
        r"Aktenzeichen\s*(?:\n|\s)+([A-Z]{2,5}-\d{6}-\d+)",
        full,
    )

    if not data["AKTENZEICHEN"]:
        data["AKTENZEICHEN"] = _search(
            r"Rechnung Nr\.?\s*([A-Z]{2,5}-\d{6}-\d+)",
            full,
        )

    # ===================================================
    # ANSPRUCHSTELLER (Firma + Geschäftsführer)
    # ===================================================
    # Im Gutachten:
    # Name Kraftverkehr Leipzig GmbH
    # Herr Berthold Richter
    # Straße An der Autobahn 1b

    m = re.search(
        r"(?:Anspruchsteller\s+)?Name\s+(.+?)\n(Herrn?|Herr|Frau)\s+(.+?)\nStraße",
        seite5,
        re.S | re.I,
    )

    if m:
        firma = m.group(1).strip()
        anrede_raw = m.group(2).strip().lower()
        person = m.group(3).strip()

        anrede = "Frau" if anrede_raw.startswith("frau") else "Herr"

        data["MANDANT_ANREDE"] = anrede

        # Firma bleibt Firma
        data["MANDANT_NAME"] = firma
        data["MANDANT_FIRMA"] = firma

        # Gewünschte Word-Logik:
        # Vorname = Person + Geschäftsführer von
        # Nachname = Unternehmen
        data["MANDANT_VORNAME"] = f"{person} Geschäftsführer von"
        data["MANDANT_NACHNAME"] = firma
        data["MANDANT_VOLLNAME"] = f"{person} Geschäftsführer von {firma}"

    # ===================================================
    # ADRESSE ANSPRUCHSTELLER (Seite 5)
    # ===================================================

    m = re.search(
        r"(?:Anspruchsteller\s+)?Name\s+.+?\n"
        r"(?:Herrn?|Herr|Frau)\s+.+?\n"
        r"Straße\s+(.+?)\n"
        r"PLZ Ort\s+(.+?)\n",
        seite5,
        re.S | re.I,
    )

    if m:
        data["MANDANT_STRASSE"] = m.group(1).strip()
        data["MANDANT_PLZ_ORT"] = m.group(2).strip()

    # ===================================================
    # UNFALL
    # ===================================================

    data["UNFALL_DATUM"] = _search(
        r"Unfall\s+Datum\s*[: ]*\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
        seite5,
    )

    # ALT war zu allgemein und hat 06184 Kabelsketal erwischt.
    # NEU sucht nur im Unfall-Block.
    data["UNFALL_ORT"] = _search(
        r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\n"
        r"Ort\s+(.+?)"
        r"(?:\nDatum\s+\d{2}\.\d{2}\.\d{4}|\nBesichtigung|\Z)",
        seite5,
    )
    data["UNFALL_ORT"] = _one_line(data["UNFALL_ORT"])

    # ===================================================
    # VERSICHERUNG
    # ===================================================
    # ALT hat bei VER_ORT zu viel mitgenommen.
    # NEU trennt Ort, Versicherungsnummer und Schadennummer sauber.

    vers = re.search(
        r"Unfallgegner.*?"
        r"Kennzeichen\s+.+?\n"
        r"Name\s+(.+?)\n"
        r"Straße\s+(.+?)\n"
        r"PLZ\s+Ort\s+(.+?)\n"
        r"Telefon\s+.*?\n"
        r"E-Mail\s+.*?\n"
        r"Versicherungs-Nr\.\s+(.+?)\n"
        r"(?:Versicherung\s*\n)?Schadennummer\s+(.+?)(?:\nDatum|\nAuftrag|\Z)",
        seite5,
        re.S | re.I,
    )

    if vers:
        data["VERSICHERUNG"] = vers.group(1).strip()
        data["VER_STRASSE"] = vers.group(2).strip()
        data["VER_ORT"] = vers.group(3).strip()
        data["VERSICHERUNGSNUMMER"] = _one_line(vers.group(4))
        data["SCHADENSNUMMER"] = _one_line(vers.group(5))

    # ===================================================
    # FAHRZEUG
    # ===================================================

    hersteller = _search(
        r"Hersteller\s+(.+?)\n(?:Modell|Modell/Haupttyp)",
        full,
    )

    modell = _search(
        r"Modell(?:/Haupttyp)?\s+(.+?)\n",
        full,
    )

    data["FAHRZEUGTYP"] = _one_line(
        " ".join(x for x in [hersteller, modell] if x)
    )

    # ALT suchte "Eigenes Kennzeichen".
    # Im NFZ-Gutachten steht aber "Amtliches Kennzeichen".
    data["KENNZEICHEN_MANDANT"] = _search(
        r"Amtliches\s+Kennzeichen\s+(.+?)\n",
        full,
    )

    data["KENNZEICHEN_MANDANT"] = _one_line(data["KENNZEICHEN_MANDANT"])
    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    data["KENNZEICHEN_GEGNER"] = _search(
        r"Unfallgegner.*?Kennzeichen\s+(.+?)\n",
        seite5,
    )
    data["KENNZEICHEN_GEGNER"] = _one_line(data["KENNZEICHEN_GEGNER"])

    # ===================================================
    # VORSTEUER
    # ===================================================

    data["VORSTEUERABZUG_RAW"] = _search(
        r"Vorsteuerabzug\s+(Ja|Nein)",
        seite5,
    )

    if data["VORSTEUERABZUG_RAW"].lower() == "ja":
        data["VORSTEUERBERECHTIGUNG"] = ""
    elif data["VORSTEUERABZUG_RAW"].lower() == "nein":
        data["VORSTEUERBERECHTIGUNG"] = "nicht"
    else:
        data["VORSTEUERBERECHTIGUNG"] = ""

    # ===================================================
    # FAHRZEUGWERT (Seite 4)
    # ===================================================

    data["WBW"] = gx._extract_money(
        seite4,
        [
            r"Wiederbeschaffungswert\s*\(regelbesteuert\)\s*([0-9]+\.[0-9]{3},[0-9]{2}\s*€)",
            r"Wiederbeschaffungswert.*?([0-9]+\.[0-9]{3},[0-9]{2}\s*€)",
        ],
    )

    data["RESTWERT"] = gx._extract_money(
        full,
        [
            r"Restwert inkl\. MwSt\.?\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€)",
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
    # ALT suchte nur "Anspruchsteller".
    # Im Gutachten steht aber "Nach Angaben des Fahrzeughalters".

    data["SCHADENHERGANG"] = _search(
        r"Schadenhergang\s+"
        r"(Nach Angaben .+?)"
        r"(?:\nAnstoß-/Schadenbereich|\nSchadenbeschreibung|\nPlausibilität|\Z)",
        full,
    )

    data["SCHADENHERGANG"] = _one_line(data["SCHADENHERGANG"])

    return data
