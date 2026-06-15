from __future__ import annotations

from typing import Dict, Any, Iterable
import re

import gutachten_extractor as gx


def _search(pattern: str, text: str, flags: int = re.S | re.I) -> str:
    m = re.search(pattern, text or "", flags)
    return m.group(1).strip() if m else ""


def _one_line(value: str) -> str:
    return " ".join((value or "").split())


def _find_page(pages, needles: Iterable[str], excludes: Iterable[str] = ()) -> str:
    for page in pages:
        p = page.lower()
        if all(n.lower() in p for n in needles) and not any(e.lower() in p for e in excludes):
            return page
    return ""


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:

    full = "\n".join(pages)

    seite4 = pages[3] if len(pages) >= 4 else full
    seite5 = _find_page(
        pages,
        ["Beteiligte, Besichtigungen & Auftrag", "Vorsteuerabzug"],
    ) or (pages[4] if len(pages) >= 5 else full)

    seite7 = _find_page(
        pages,
        ["Fahrzeugdaten", "Amtliches Kennzeichen"],
    ) or (pages[6] if len(pages) >= 7 else full)

    seite_schadenhergang = _find_page(
        pages,
        ["Schadenhergang", "Nach Angaben"],
        excludes=["Inhaltsverzeichnis"],
    ) or full

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
    # ANSPRUCHSTELLER / FIRMA / PERSON
    # ===================================================

    m = re.search(
        r"(?:Anspruchsteller\s+)?Name\s+(.+?)\n"
        r"(Herrn?|Herr|Frau)\s+(.+?)\n"
        r"Straße\s+(.+?)\n"
        r"PLZ Ort\s+(.+?)(?:\nAnspruchsteller|\nVorsteuerabzug)",
        seite5,
        re.S | re.I,
    )

    if m:
        firma = m.group(1).strip()
        anrede_raw = m.group(2).strip().lower()
        person = m.group(3).strip()

        data["MANDANT_ANREDE"] = "Frau" if anrede_raw.startswith("frau") else "Herr"
        data["MANDANT_NAME"] = firma
        data["MANDANT_FIRMA"] = firma

        data["MANDANT_VORNAME"] = f"{person} Geschäftsführer von"
        data["MANDANT_NACHNAME"] = firma
        data["MANDANT_VOLLNAME"] = f"{person} Geschäftsführer von {firma}"

        data["MANDANT_STRASSE"] = m.group(4).strip()
        data["MANDANT_PLZ_ORT"] = m.group(5).strip()

    # ===================================================
    # UNFALL
    # ===================================================

    data["UNFALL_DATUM"] = _search(
        r"Unfall\s+Datum\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
        seite5,
    )

    unfall_ort_raw = _search(
        r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\n"
        r"(.+?)"
        r"(?:\nDatum\s+\d{2}\.\d{2}\.\d{4}|\nBesichtigung|\Z)",
        seite5,
    )

    # pdfplumber kann "Ort" nach der Adresse liefern:
    # HL Freight ... 63526
    # Ort Erlensee
    unfall_ort_raw = re.sub(r"(?im)^\s*Ort\s*", "", unfall_ort_raw)

    data["UNFALL_ORT"] = _one_line(unfall_ort_raw)

    # ===================================================
    # VERSICHERUNG
    # ===================================================

    data["VERSICHERUNG"] = _search(
        r"Versicherung\s+Name\s+([^\n]+)",
        seite5,
        re.I | re.M,
    )

    data["VER_STRASSE"] = _search(
        r"Versicherung\s+Name\s+[^\n]+\n"
        r"Straße\s+([^\n]+)",
        seite5,
        re.I | re.M,
    )

    data["VER_ORT"] = _search(
        r"Versicherung\s+Name\s+[^\n]+\n"
        r"Straße\s+[^\n]+\n"
        r"PLZ Ort\s+([^\n]+)",
        seite5,
        re.I | re.M,
    )

    data["VERSICHERUNGSNUMMER"] = _search(
        r"Versicherungs-Nr\.\s+([^\n]+)",
        seite5,
        re.I | re.M,
    )

    data["SCHADENSNUMMER"] = _search(
        r"(?:^|\n)(?:Versicherung\s*\n)?Schadennummer\s+([^\n]+)",
        seite5,
        re.I | re.M,
    )

    data["SCHADENSNUMMER"] = _one_line(data["SCHADENSNUMMER"])

    # ===================================================
    # FAHRZEUG
    # ===================================================

    data["KENNZEICHEN_MANDANT"] = _search(
        r"^Amtliches Kennzeichen\s+([^\n]+)",
        seite7,
        re.I | re.M,
    )

    data["KENNZEICHEN_MANDANT"] = _one_line(data["KENNZEICHEN_MANDANT"])
    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    data["KENNZEICHEN_GEGNER"] = _search(
        r"Unfallgegner.*?Kennzeichen\s+([^\n]+)",
        seite5,
        re.S | re.I,
    )

    data["KENNZEICHEN_GEGNER"] = _one_line(data["KENNZEICHEN_GEGNER"])

    hersteller = _search(
        r"^Hersteller\s+([^\n]+)",
        seite7,
        re.I | re.M,
    )

    modell = _search(
        r"^Modell(?:/Haupttyp)?\s+([^\n]+)",
        seite7,
        re.I | re.M,
    )

    # Fallback für Deckblatt-Seite:
    # Hersteller
    # Schmitz Cargobull
    # Modell
    # SKO
    if not hersteller:
        hersteller = _search(
            r"^Hersteller\s*\n([^\n]+)",
            full,
            re.I | re.M,
        )

    if not modell:
        modell = _search(
            r"^Modell\s*\n([^\n]+)",
            full,
            re.I | re.M,
        )

    data["FAHRZEUGTYP"] = _one_line(
        " ".join(x for x in [hersteller, modell] if x)
    )

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
    # REPARATURKOSTEN / SCHADENHÖHE
    # ===================================================

    data["REPARATURKOSTEN_NETTO"] = gx._extract_money(
        seite4,
        [
            r"Reparaturkosten ohne MwSt\.\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
            r"Schadenhöhe ohne MwSt\.\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = gx._extract_money(
        seite4,
        [
            r"Schadenhöhe inkl\. MwSt\.\s*\([^)]*\)\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
            r"Reparaturkosten inkl\. MwSt\.\s*\([^)]*\)\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )

    # ===================================================
    # FAHRZEUGWERT
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
        r"^Schadenhergang\s*\n?"
        r"(Nach Angaben .+?)"
        r"(?:\nAnstoß-/Schadenbereich|\nSchadenbeschreibung|\nPlausibilität|\Z)",
        seite_schadenhergang,
        re.S | re.I | re.M,
    )

    data["SCHADENHERGANG"] = _one_line(data["SCHADENHERGANG"])

    return data
