from __future__ import annotations

from typing import Dict, Any
import re

import gutachten_extractor as gx


def _search(pattern: str, text: str) -> str:
    m = re.search(pattern, text or "", re.S | re.I)
    return m.group(1).strip() if m else ""


def _one_line(value: str) -> str:
    return " ".join((value or "").split())


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:

    full = "\n".join(pages)

    seite4 = pages[3] if len(pages) >= 4 else full
    seite5 = pages[4] if len(pages) >= 5 else full
    seite7 = pages[6] if len(pages) >= 7 else full
    seite8 = pages[7] if len(pages) >= 8 else full

    data: Dict[str, Any] = {}
    data["_PARSER"] = "nfz_totalschaden"

    # ===================================================
    # AKTENZEICHEN
    # ===================================================

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

    m = re.search(
        r"(?:Anspruchsteller\s+)?Name\s+(.+?)\n"
        r"(Herrn?|Herr|Frau)\s+(.+?)\n"
        r"Straße\s+(.+?)\n"
        r"PLZ Ort\s+(.+?)\n",
        seite5,
        re.S | re.I,
    )

    if m:
        firma = m.group(1).strip()
        anrede_raw = m.group(2).strip()
        person = m.group(3).strip()

        if anrede_raw.lower().startswith("frau"):
            anrede = "Frau"
        else:
            anrede = "Herr"

        data["MANDANT_ANREDE"] = anrede

        data["MANDANT_NAME"] = firma
        data["MANDANT_FIRMA"] = firma

        # Deine gewünschte Logik:
        data["MANDANT_VORNAME"] = f"{person} Geschäftsführer von"
        data["MANDANT_NACHNAME"] = firma
        data["MANDANT_VOLLNAME"] = f"{person} Geschäftsführer von {firma}"

        data["MANDANT_STRASSE"] = m.group(4).strip()
        data["MANDANT_PLZ_ORT"] = m.group(5).strip()

    # ===================================================
    # UNFALL
    # ===================================================

    data["UNFALL_DATUM"] = _search(
        r"Unfall\s+Datum\s*[: ]*\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
        seite5,
    )

    # Nimmt alles zwischen "Unfall Datum ..." und "Besichtigung Datum ..."
    # und entfernt danach das störende "Ort"-Label.
    unfall_block = _search(
        r"Unfall\s+Datum\s+[0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*(.*?)(?:Besichtigung\s+Datum|Datum\s+[0-9]{2}\.[0-9]{2}\.[0-9]{4}\s+-|\Z)",
        seite5,
    )

    unfall_block = re.sub(r"\bOrt\b", " ", unfall_block, flags=re.I)
    data["UNFALL_ORT"] = _one_line(unfall_block)

    # ===================================================
    # VERSICHERUNG
    # ===================================================

    # Erst Versicherungsblock isolieren: ab Gegner-Kennzeichen bis Auftrag.
    vers_block = _search(
        r"Unfallgegner.*?Kennzeichen\s+.+?\n(.*?)(?:\nAuftrag|\nDatum\s+[0-9]{2}\.[0-9]{2}\.[0-9]{4}\nErteilt|\Z)",
        seite5,
    )

    if not vers_block:
        vers_block = seite5

    data["VERSICHERUNG"] = _search(
        r"(?:Versicherung\s+)?Name\s+(.+?)\n",
        vers_block,
    )

    data["VER_STRASSE"] = _search(
        r"Straße\s+(.+?)\n",
        vers_block,
    )

    data["VER_ORT"] = _search(
        r"PLZ\s+Ort\s+(.+?)\n",
        vers_block,
    )

    data["VERSICHERUNGSNUMMER"] = _search(
        r"Versicherungs-Nr\.\s+(.+?)\n",
        vers_block,
    )

    data["SCHADENSNUMMER"] = _search(
        r"Schadennummer\s+(.+?)(?:\n|$)",
        vers_block,
    )

    data["SCHADENSNUMMER"] = _one_line(data["SCHADENSNUMMER"])

    # ===================================================
    # FAHRZEUG
    # ===================================================

    hersteller = _search(
        r"Hersteller\s+([^\n]+)",
        seite7,
    )

    modell = _search(
        r"Modell(?:/Haupttyp)?\s+([^\n]+)",
        seite7,
    )

    data["FAHRZEUGTYP"] = _one_line(
        " ".join(x for x in [hersteller, modell] if x)
    )

    data["KENNZEICHEN_MANDANT"] = _search(
        r"Amtliches\s+Kennzeichen\s+([^\n]+)",
        seite7,
    )

    data["KENNZEICHEN_MANDANT"] = _one_line(data["KENNZEICHEN_MANDANT"])

    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    data["KENNZEICHEN_GEGNER"] = _search(
        r"Unfallgegner.*?Kennzeichen\s+([^\n]+)",
        seite5,
    )

    data["KENNZEICHEN_GEGNER"] = _one_line(data["KENNZEICHEN_GEGNER"])

    # ===================================================
    # VORSTEUER
    # ===================================================

    data["VORSTEUERABZUG_RAW"] = _search(
        r"Vorsteuerabzug.*?(Ja|Nein)",
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
            r"Wiederbeschaffungswert\s*\(regelbesteuert\)\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
            r"Wiederbeschaffungswert.*?([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )

    data["RESTWERT"] = gx._extract_money(
        seite4,
        [
            r"Restwert inkl\. MwSt\.?\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
            r"Restwert.*?([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )

    # ===================================================
    # SONDERKOSTEN
    # ===================================================

    data["MELDUNGSKOSTEN"] = gx._extract_money(
        seite4,
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
        r"Schadenhergang\s+"
        r"(Nach Angaben .+?)"
        r"(?:\nAnstoß-/Schadenbereich|\nSchadenbeschreibung|\nPlausibilität|\Z)",
        full,
    )

    data["SCHADENHERGANG"] = _one_line(data["SCHADENHERGANG"])

    return data
