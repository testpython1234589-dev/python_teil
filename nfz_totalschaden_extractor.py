from __future__ import annotations

from typing import Dict, Any, Iterable
import re

import gutachten_extractor as gx


_FLAGS = re.IGNORECASE | re.MULTILINE | re.DOTALL


def _clean(value: str) -> str:
    return gx._clean_text(value or "")


def _one_line(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _search(pattern: str, text: str) -> str:
    m = re.search(pattern, text or "", _FLAGS)
    return _clean(m.group(1)) if m else ""


def _search_first(text: str, patterns: Iterable[str]) -> str:
    for pattern in patterns:
        value = _search(pattern, text)
        if value:
            return value
    return ""


def _find_page(pages, needles: Iterable[str], excludes: Iterable[str] = ()) -> str:
    for page in pages:
        page_lower = page.lower()
        if all(n.lower() in page_lower for n in needles) and not any(e.lower() in page_lower for e in excludes):
            return page
    return ""


def _normalize_plate(value: str) -> str:
    value = (value or "").replace(":", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip().upper()


def _clean_unfall_ort(value: str) -> str:
    value = _one_line(value)
    value = re.sub(r"\bOrt\b", " ", value, flags=re.IGNORECASE)
    return _one_line(value)


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)

    p_invoice = _find_page(
        pages,
        ["Rechnung Nr.", "Gesamtbetrag ohne MwSt."],
    ) or (pages[0] if pages else full)

    p_summary = _find_page(
        pages,
        ["Zusammenfassung", "Totalschaden"],
        excludes=["Inhaltsverzeichnis"],
    ) or (pages[3] if len(pages) >= 4 else full)

    p_beteiligte = _find_page(
        pages,
        ["Beteiligte, Besichtigungen & Auftrag", "Vorsteuerabzug"],
    ) or (pages[4] if len(pages) >= 5 else full)

    p_vehicle = _find_page(
        pages,
        ["Fahrzeugdaten", "Amtliches Kennzeichen"],
    ) or full

    p_schadenhergang = _find_page(
        pages,
        ["Schadenhergang", "Nach Angaben"],
        excludes=["Inhaltsverzeichnis"],
    ) or full

    p_wbw = _find_page(
        pages,
        ["Wiederbeschaffungswert"],
        excludes=["Inhaltsverzeichnis", "Zusammenfassung"],
    ) or ""

    data: Dict[str, Any] = {}
    data["_PARSER"] = "nfz_totalschaden"

    # ===================================================
    # AKTENZEICHEN
    # ===================================================

    data["AKTENZEICHEN"] = _search_first(
        full,
        [
            r"Rechnung Nr\.?\s*(NFZ-[0-9-]+)",
            r"Aktenzeichen\s+(NFZ-[0-9-]+)",
            r"Aktenzeichen\s*\n\s*(NFZ-[0-9-]+)",
        ],
    )

    # ===================================================
    # ANSPRUCHSTELLER: Firma + Person
    # ===================================================

    m = re.search(
        r"Anspruchsteller\s+Name\s+(.+?)\n(Herrn?|Frau)\s+(.+?)\nStraße",
        p_beteiligte,
        _FLAGS,
    )

    if not m:
        m = re.search(
            r"Anspruchsteller\s*\n(.+?)\n(Herrn?|Frau)\s+(.+?)\n",
            full,
            _FLAGS,
        )

    if m:
        firma = _clean(m.group(1))
        anrede_raw = _clean(m.group(2)).lower()
        person = _clean(m.group(3))

        anrede = "Frau" if anrede_raw.startswith("frau") else "Herr"

        data["_NFZ_MANDANT_FIRMA"] = firma
        data["_NFZ_MANDANT_PERSON"] = person

        data["MANDANT_ANREDE"] = anrede
        data["MANDANT_NAME"] = firma
        data["MANDANT_FIRMA"] = firma

        # Gewünschte Word-Logik:
        # {MANDANT_VORNAME} {MANDANT_NACHNAME}
        # = Berthold Richter Geschäftsführer von Kraftverkehr Leipzig GmbH
        data["MANDANT_VORNAME"] = f"{person} Geschäftsführer von"
        data["MANDANT_NACHNAME"] = firma
        data["MANDANT_VOLLNAME"] = f"{person} Geschäftsführer von {firma}"

    # ===================================================
    # ADRESSE ANSPRUCHSTELLER
    # ===================================================

    data["MANDANT_STRASSE"] = _search_first(
        p_beteiligte,
        [
            r"Anspruchsteller\s+Name\s+.+?\n(?:Herrn?|Frau)\s+.+?\nStraße\s+(.+?)\nPLZ Ort",
            r"\nStraße\s+(.+?)\nPLZ Ort",
        ],
    )

    data["MANDANT_PLZ_ORT"] = _search_first(
        p_beteiligte,
        [
            r"Anspruchsteller\s+Name\s+.+?\n(?:Herrn?|Frau)\s+.+?\nStraße\s+.+?\nPLZ Ort\s+(.+?)\nVorsteuerabzug",
            r"\nPLZ Ort\s+(.+?)\nVorsteuerabzug",
        ],
    )

    # ===================================================
    # UNFALL
    # ===================================================

    data["UNFALL_DATUM"] = _search_first(
        p_beteiligte,
        [
            r"Unfall\s+Datum\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    unfall_ort_raw = _search_first(
        p_beteiligte,
        [
            r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\nOrt\s+(.+?)(?:\nBesichtigung\s+Datum|\nDatum\s+\d{2}\.\d{2}\.\d{4}|\Z)",
            r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\n(.+?)(?:\nBesichtigung\s+Datum|\nDatum\s+\d{2}\.\d{2}\.\d{4}|\Z)",
        ],
    )

    data["UNFALL_ORT"] = _clean_unfall_ort(unfall_ort_raw)

    # ===================================================
    # VERSICHERUNG
    # ===================================================

    vers_text = p_beteiligte

    m_block = re.search(
        r"Unfallgegner.*?Kennzeichen\s+.+?\n(?P<block>.*?)(?:\nAuftrag\b|\Z)",
        p_beteiligte,
        _FLAGS,
    )

    if m_block:
        vers_text = m_block.group("block")

    vers = re.search(
        r"(?:Versicherung\s+)?Name\s+(.+?)\n"
        r"Straße\s+(.+?)\n"
        r"PLZ Ort\s+(.+?)\n"
        r"Telefon.*?\n"
        r"E-Mail.*?\n"
        r"Versicherungs-Nr\.?\s+(.+?)\n"
        r"(?:Versicherung\s*\n)?Schadennummer\s+(.+?)(?:\n(?:Auftrag|Datum)\b|\Z)",
        vers_text,
        _FLAGS,
    )

    if vers:
        data["VERSICHERUNG"] = _clean(vers.group(1))
        data["VER_STRASSE"] = _clean(vers.group(2))
        data["VER_ORT"] = _clean(vers.group(3))
        data["VERSICHERUNGSNUMMER"] = _clean(vers.group(4))

        schadennummer = " ".join(_clean(vers.group(5)).split())
        data["SCHADENSNUMMER"] = schadennummer
        data["_NFZ_SCHADENSNUMMER_RAW"] = schadennummer

    # ===================================================
    # FAHRZEUG
    # ===================================================

    hersteller = _search_first(
        p_vehicle,
        [
            r"Hersteller\s+(.+?)\n",
        ],
    )

    modell = _search_first(
        p_vehicle,
        [
            r"Modell(?:/Haupttyp)?\s+(.+?)\n",
        ],
    )

    data["FAHRZEUGTYP"] = _one_line(" ".join(x for x in [hersteller, modell] if x))

    kennzeichen_mandant = _search_first(
        p_vehicle + "\n" + p_invoice + "\n" + p_summary,
        [
            r"Amtliches Kennzeichen\s+(.+?)\n",
            r"\nKennzeichen\s+([A-ZÄÖÜ]{1,3}[:\s]+[A-ZÄÖÜ]{1,3}\s*\d{1,4})",
            r"\b([A-ZÄÖÜ]{1,3}[:\s]+[A-ZÄÖÜ]{1,3}\s*\d{1,4})\b",
        ],
    )

    data["KENNZEICHEN_MANDANT"] = _normalize_plate(kennzeichen_mandant)
    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    kennzeichen_gegner = _search_first(
        p_beteiligte,
        [
            r"Unfallgegner.*?Kennzeichen\s+(.+?)\n",
        ],
    )

    data["KENNZEICHEN_GEGNER"] = _normalize_plate(kennzeichen_gegner)

    # ===================================================
    # VORSTEUER
    # ===================================================

    data["VORSTEUERABZUG_RAW"] = _search_first(
        p_beteiligte,
        [
            r"Vorsteuerabzug\s+(Ja|Nein)",
        ],
    )

    # derive_fields macht daraus später "" oder "nicht"
    if data["VORSTEUERABZUG_RAW"].lower() == "ja":
        data["VORSTEUERBERECHTIGUNG"] = ""
    elif data["VORSTEUERABZUG_RAW"].lower() == "nein":
        data["VORSTEUERBERECHTIGUNG"] = "nicht"
    else:
        data["VORSTEUERBERECHTIGUNG"] = ""

    # ===================================================
    # FAHRZEUGWERT
    # ===================================================

    wert_text = p_summary + "\n" + p_wbw + "\n" + full

    data["WBW"] = gx._extract_money(
        wert_text,
        [
            r"Wiederbeschaffungswert\s*\(regelbesteuert\)\s*([0-9\., ]+€?)",
            r"Wiederbeschaffungswert\s*\(differenzbesteuert\)\s*([0-9\., ]+€?)",
            r"Wiederbeschaffungswert\s*\(steuerneutral\)\s*([0-9\., ]+€?)",
            r"Wiederbeschaffungswert:\s*([0-9\., ]+€?)",
            r"Wiederbeschaffungswert\s+([0-9\., ]+€?)",
        ],
    )

    data["RESTWERT"] = gx._extract_money(
        wert_text,
        [
            r"Restwert inkl\. MwSt\.?\s*([0-9\., ]+€?)",
            r"Restwert:\s*([0-9\., ]+€?)",
            r"Restwert\s+([0-9\., ]+€?)",
        ],
    )

    # ===================================================
    # SONDERKOSTEN
    # ===================================================

    data["MELDUNGSKOSTEN"] = gx._extract_money(
        wert_text,
        [
            r"Ab-\s*&\s*Anmeldegebühren\s*([0-9\., ]+€?)",
            r"Gebühren:\s*([0-9\., ]+€?)",
        ],
    )

    # ===================================================
    # GUTACHTERKOSTEN
    # ===================================================

    data["GUTACHTERKOSTEN_NETTO"] = gx._extract_money(
        p_invoice,
        [
            r"Gesamtbetrag ohne MwSt\.\s*([0-9\., ]+€?)",
        ],
    )

    data["GUTACHTERKOSTEN_BRUTTO"] = gx._extract_money(
        p_invoice,
        [
            r"Gesamtbetrag inkl\. MwSt\.\s*([0-9\., ]+€?)",
        ],
    )

    # ===================================================
    # SCHADENHERGANG
    # ===================================================

    data["SCHADENHERGANG"] = _one_line(
        _search_first(
            p_schadenhergang,
            [
                r"Schadenhergang\s+(Nach Angaben .+?)(?:\nAnstoß-/Schadenbereich|\nSchadenbeschreibung|\nPlausibilität|\Z)",
                r"Nach Angaben (.+?)(?:\nAnstoß-/Schadenbereich|\nSchadenbeschreibung|\nPlausibilität|\Z)",
            ],
        )
    )

    return data


def apply_nfz_totalschaden_overrides(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wichtig:
    Diese Funktion NACH gx.derive_fields(...) aufrufen,
    weil derive_fields MANDANT_VORNAME, MANDANT_NACHNAME,
    MANDANT_VOLLNAME und SCHADENSNUMMER sonst wieder überschreibt.
    """

    if data.get("_PARSER") != "nfz_totalschaden":
        return data

    firma = str(data.get("_NFZ_MANDANT_FIRMA") or data.get("MANDANT_FIRMA") or "").strip()
    person = str(data.get("_NFZ_MANDANT_PERSON") or "").strip()

    if firma and person:
        data["MANDANT_NAME"] = firma
        data["MANDANT_FIRMA"] = firma
        data["MANDANT_TITEL"] = ""

        data["MANDANT_VORNAME"] = f"{person} Geschäftsführer von"
        data["MANDANT_NACHNAME"] = firma
        data["MANDANT_VOLLNAME"] = f"{person} Geschäftsführer von {firma}"

    schadennummer = str(data.get("_NFZ_SCHADENSNUMMER_RAW") or "").strip()
    if schadennummer:
        data["SCHADENSNUMMER"] = schadennummer

    # Damit diese technischen Hilfsfelder nicht in Streamlit/Word stören
    data.pop("_NFZ_MANDANT_FIRMA", None)
    data.pop("_NFZ_MANDANT_PERSON", None)
    data.pop("_NFZ_SCHADENSNUMMER_RAW", None)

    return data
