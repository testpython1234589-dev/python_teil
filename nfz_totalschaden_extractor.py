from __future__ import annotations

from typing import Dict, Any, Iterable
import re

import gutachten_extractor as gx


def _search(pattern: str, text: str, flags: int = re.S | re.I) -> str:
    m = re.search(pattern, text or "", flags)
    return m.group(1).strip() if m else ""


def _one_line(value: str) -> str:
    return " ".join((value or "").split())

def _extract_nfz_schadensnummer(*texts: str) -> str:
    """
    Erkennt NFZ-Schadennummern wie:
    SD2 0003 5413 44 T01

    Funktioniert sowohl im Beteiligten-Block:
    Schadennummer SD2 0003 5413 44 T01

    als auch auf der Rechnung:
    Schaden-Nr.
    Versicherungs-Nr.
    SD2 0003 5413 44 T01
    K 576-611645/61
    """

    patterns = [
        # Beteiligtenblock, normal oder flach extrahiert
        r"\bSchadennummer\s*[:\-]?\s+([A-Z0-9]{2,5}(?:\s+[A-Z0-9]{2,6}){2,6})(?=\s+(?:Auftrag|Datum|Erteilt|Beauftragung)\b|$)",

        # Rechnung: Schaden-Nr. Versicherungs-Nr. SD2 ... K 576...
        r"\bSchaden-Nr\.\s+Versicherungs-Nr\.\s+([A-Z0-9]{2,5}(?:\s+[A-Z0-9]{2,6}){2,6})\s+K\s+\d",

        # Fallback: etwas freier, aber stoppt vor Auftrag/Datum
        r"\bSchadennummer\s*[:\-]?\s+([A-Z0-9][A-Z0-9 ]{5,40}?)(?=\s+(?:Auftrag|Datum|Erteilt|Beauftragung)\b|$)",
    ]

    for text in texts:
        flat = _one_line(text)

        for pattern in patterns:
            m = re.search(pattern, flat, re.I)
            if not m:
                continue

            value = _one_line(m.group(1))

            # Sicherheits-Cleanup, falls doch etwas zu viel mitkommt
            value = re.sub(
                r"\b(?:Auftrag|Datum|Erteilt|Beauftragung|Versicherung)\b.*$",
                "",
                value,
                flags=re.I,
            ).strip()

            # Versicherungsnummer nicht aus Versehen nehmen
            if value and not value.startswith("K "):
                return value

    return ""


def _find_page(
    pages,
    needles: Iterable[str],
    excludes: Iterable[str] = (),
) -> str:
    for page in pages:
        page_lower = page.lower()

        if all(n.lower() in page_lower for n in needles) and not any(
            e.lower() in page_lower for e in excludes
        ):
            return page

    return ""


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)

    seite_rechnung = _find_page(
        pages,
        ["Rechnung Nr.", "Gesamtbetrag ohne MwSt."],
    ) or (pages[0] if len(pages) >= 1 else full)

    seite4 = _find_page(
        pages,
        ["Zusammenfassung", "Totalschaden"],
        excludes=["Inhaltsverzeichnis"],
    ) or (pages[3] if len(pages) >= 4 else full)

    seite5 = _find_page(
        pages,
        ["Beteiligte, Besichtigungen & Auftrag", "Vorsteuerabzug"],
    ) or (pages[4] if len(pages) >= 5 else full)

    seite_fahrzeug = _find_page(
        pages,
        ["Fahrzeugdaten", "Amtliches Kennzeichen"],
        excludes=["Inhaltsverzeichnis"],
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
    # ANSPRUCHSTELLER / FIRMA / GESCHÄFTSFÜHRER
    # ===================================================

    m = re.search(
        r"(?:Anspruchsteller\s+)?Name\s+(.+?)\n"
        r"(Herrn?|Herr|Frau)\s+(.+?)\n"
        r"Straße\s+(.+?)\n"
        r"PLZ Ort\s+(.+?)(?:\nAnspruchsteller|\nVorsteuerabzug|\n)",
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

        # Gewünschte Word-Logik:
        # {MANDANT_VORNAME} {MANDANT_NACHNAME}
        # = Berthold Richter Geschäftsführer von Kraftverkehr Leipzig GmbH
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

    # Wichtig:
    # Der Unfallort ist im PDF nicht immer stabil als "Ort\nWert".
    # Deshalb: Block zwischen Unfall Datum und Besichtigung nehmen,
    # dann das Label "Ort" entfernen.
    unfall_block = _search(
        r"Unfall\s+Datum\s+[0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*"
        r"(.*?)"
        r"(?:\nDatum\s+[0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*-|\nBesichtigung\s+Datum|\bBesichtigung\s+Datum|\nBesichtigung\b|\Z)",
        seite5,
    )

    unfall_block = re.sub(r"\bOrt\b", " ", unfall_block, flags=re.I)
    data["UNFALL_ORT"] = _one_line(unfall_block)

    # ===================================================
    # VERSICHERUNG
    # ===================================================

    # Erst nur den Versicherungsbereich isolieren:
    # nach Unfallgegner/Kennzeichen bis Auftrag bzw. Datum/Erteilt.
    vers_block = _search(
        r"Unfallgegner\b.*?"
        r"Kennzeichen\s+[^\n]+\n"
        r"(.*?)"
        r"(?:\nAuftrag\b|\nDatum\s+[0-9]{2}\.[0-9]{2}\.[0-9]{4}\s*\nErteilt|\Z)",
        seite5,
    )

    # Fallback, falls PDF-Text anders sortiert ist.
    if not vers_block:
        vers_block = _search(
            r"((?:Versicherung\s+)?Name\s+[^\n]+\n"
            r"Straße\s+[^\n]+\n"
            r"PLZ\s+Ort\s+[^\n]+\n"
            r"Telefon\s+[^\n]*\n"
            r"E-Mail\s+[^\n]*\n"
            r"Versicherungs-Nr\.\s+[^\n]+"
            r"(?:\nVersicherung)?\n"
            r"Schadennummer\s+[^\n]+)",
            seite5,
        )

    data["VERSICHERUNG"] = _search(
        r"(?:^|\n)(?:Versicherung\s+)?Name\s+([^\n]+)",
        vers_block,
        re.I | re.M,
    )

    data["VER_STRASSE"] = _search(
        r"(?:^|\n)Straße\s+([^\n]+)",
        vers_block,
        re.I | re.M,
    )

    data["VER_ORT"] = _search(
        r"(?:^|\n)PLZ\s+Ort\s+([^\n]+)",
        vers_block,
        re.I | re.M,
    )

    data["VERSICHERUNGSNUMMER"] = _search(
        r"Versicherungs-Nr\.\s+([^\n]+)",
        vers_block,
        re.I | re.M,
    )
    data["SCHADENSNUMMER"] = _extract_nfz_schadensnummer(
        vers_block,
        seite5,
        full,
    )

    data["SCHADENSNUMMER"] = _one_line(data["SCHADENSNUMMER"])

    # ===================================================
    # FAHRZEUG
    # ===================================================

    # Wichtig:
    # Nur auf der Fahrzeugdaten-Seite suchen, nicht auf full.
    # Sonst springt Regex seitenübergreifend.
    data["KENNZEICHEN_MANDANT"] = _search(
        r"^Amtliches Kennzeichen\s+([^\n]+)",
        seite_fahrzeug,
        re.I | re.M,
    )

    data["KENNZEICHEN_MANDANT"] = _one_line(data["KENNZEICHEN_MANDANT"])
    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    data["KENNZEICHEN_GEGNER"] = _search(
        r"Unfallgegner\b.*?Kennzeichen\s+([^\n]+)",
        seite5,
        re.S | re.I,
    )

    data["KENNZEICHEN_GEGNER"] = _one_line(data["KENNZEICHEN_GEGNER"])

    hersteller = _search(
        r"^Hersteller\s+([^\n]+)",
        seite_fahrzeug,
        re.I | re.M,
    )

    modell = _search(
        r"^Modell(?:/Haupttyp)?\s+([^\n]+)",
        seite_fahrzeug,
        re.I | re.M,
    )

    # Fallback für Deckblatt:
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

    # ===================================================
# FAHRZEUGWERT
# ===================================================
# Logik:
# Vorsteuerabzug Ja  -> netto / ohne MwSt.
# Vorsteuerabzug Nein -> brutto / inkl. MwSt.
#
# Wichtig:
# WBW und RESTWERT werden am Ende bewusst auf den passenden Wert gesetzt,
# damit derive_fields() danach automatisch richtig rechnet:
# WIEDERBESCHAFFUNGSWERTAUFWAND = WBW - RESTWERT

    wbw_brutto = gx._extract_money(
        seite4,
        [
            r"Wiederbeschaffungswert\s*\(regelbesteuert\)\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
            r"Wiederbeschaffungswert inkl\.?\s*MwSt\.?\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )
    
    wbw_netto = gx._extract_money(
        seite4,
        [
            r"Wiederbeschaffungswert ohne MwSt\.?\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )
    
    restwert_brutto = gx._extract_money(
        seite4,
        [
            r"Restwert inkl\.?\s*MwSt\.?\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )
    
    restwert_netto = gx._extract_money(
        seite4,
        [
            r"Restwert ohne MwSt\.?\s*([0-9]+(?:\.[0-9]{3})*,[0-9]{2}\s*€?)",
        ],
    )
    
    # Optional speichern, falls du später im Debug sehen willst,
    # welche Werte gefunden wurden.
    data["WBW_BRUTTO"] = wbw_brutto
    data["WBW_NETTO"] = wbw_netto
    data["RESTWERT_BRUTTO"] = restwert_brutto
    data["RESTWERT_NETTO"] = restwert_netto
    
    vorsteuer = data.get("VORSTEUERABZUG_RAW", "").strip().lower()
    
    if vorsteuer == "ja":
        data["WBW"] = wbw_netto or wbw_brutto
        data["RESTWERT"] = restwert_netto or restwert_brutto
    else:
        data["WBW"] = wbw_brutto or wbw_netto
        data["RESTWERT"] = restwert_brutto or restwert_netto
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
            seite_rechnung,
            [
                r"Gesamtbetrag ohne MwSt\.\s*([0-9\., ]+€?)",
            ],
        )
    
        data["GUTACHTERKOSTEN_BRUTTO"] = gx._extract_money(
            seite_rechnung,
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
