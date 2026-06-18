from __future__ import annotations

from typing import Dict, Any, Optional, List
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta
import re

import gutachten_extractor as gx


# ============================================================
# NFZ STANDARD – REPARATURSCHADEN
# Drop-in replacement für deine alte nfz_standard.py
#
# Erwartung:
# parse_nfz_standard(pages, pdf_source=None)
#
# pages = Liste mit PDF-Seitentexten, z. B. aus gx.pdf_to_pages(...)
# ============================================================


# ------------------------------------------------------------
# Kleine Hilfsfunktionen
# ------------------------------------------------------------

def _one_line(value: str) -> str:
    """Macht aus mehrzeiligem Text eine saubere Ein-Zeilen-Ausgabe."""
    return " ".join((value or "").replace("\xa0", " ").split())


def _clean(value: str) -> str:
    return (value or "").replace("\xa0", " ").strip()


def _search(text: str, pattern: str, flags: int = re.S | re.I) -> str:
    m = re.search(pattern, text or "", flags)
    return _clean(m.group(1)) if m else ""


def _search_first(text: str, patterns: List[str], flags: int = re.S | re.I) -> str:
    for pattern in patterns:
        value = _search(text, pattern, flags)
        if value:
            return value
    return ""


def _get_page(pages: List[str], *keywords: str) -> str:
    """
    Gibt die erste Seite zurück, die alle keywords enthält.
    Wichtig, damit z. B. der Mandant nicht aus der Rechnung gezogen wird.
    """
    for page in pages:
        low = (page or "").lower()
        if all(k.lower() in low for k in keywords):
            return page
    return ""


def _lines(text: str) -> List[str]:
    return [_clean(x) for x in (text or "").splitlines() if _clean(x)]


def _find_line_value(
    lines: List[str],
    prefix: str,
    start: int = 0,
    stop: Optional[int] = None,
) -> str:
    stop = stop if stop is not None else len(lines)
    prefix_low = prefix.lower()

    for line in lines[start:stop]:
        if line.lower().startswith(prefix_low):
            return _clean(line[len(prefix):])
    return ""


def _parse_eur(value: str) -> Optional[Decimal]:
    """
    Wandelt deutsche Geldwerte robust in Decimal um.
    Beispiele:
    1.063,00 € -> Decimal("1063.00")
    4.177,52   -> Decimal("4177.52")
    7900       -> Decimal("7900")
    """
    if not value:
        return None

    s = str(value)
    s = s.replace("€", "")
    s = s.replace("\xa0", " ")
    s = s.strip()

    # Nur Zahlbestandteile behalten
    s = re.sub(r"[^0-9,.\-]", "", s)

    if not s:
        return None

    # Deutsches Format: 1.063,00
    if "," in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    else:
        # Wenn nur Punkt vorhanden und genau 3 Stellen danach: Tausenderpunkt
        # Beispiel: 7.900 -> 7900
        if re.search(r"\.\d{3}$", s):
            s = s.replace(".", "")

    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _format_eur(value: Decimal | int | float | str | None) -> str:
    if value is None:
        return ""

    if not isinstance(value, Decimal):
        parsed = _parse_eur(str(value))
        if parsed is None:
            return ""
        value = parsed

    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{value:,.2f}"              # 1,063.00
    s = s.replace(",", "X")          # 1X063.00
    s = s.replace(".", ",")          # 1X063,00
    s = s.replace("X", ".")          # 1.063,00
    return f"{s} €"


def _extract_money(text: str, patterns: List[str]) -> str:
    raw = _search_first(text, patterns)
    return _format_eur(raw) if raw else ""


def _sum_eur(*values: str) -> str:
    total = Decimal("0.00")
    found = False

    for value in values:
        parsed = _parse_eur(value)
        if parsed is not None:
            total += parsed
            found = True

    return _format_eur(total) if found else ""


def _split_person(full_name: str) -> tuple[str, str]:
    """
    Berthold Richter -> ("Berthold", "Richter")
    Hans Peter Müller -> ("Hans Peter", "Müller")
    """
    full_name = _one_line(full_name)
    if not full_name:
        return "", ""

    parts = full_name.split()
    if len(parts) == 1:
        return "", parts[0]

    return " ".join(parts[:-1]), parts[-1]


def _normalize_anrede(anrede: str) -> str:
    a = _clean(anrede).lower()

    if a in {"herr", "herrn"}:
        return "Herr"
    if a == "frau":
        return "Frau"

    return ""


def _normalize_plate(value: str) -> str:
    """
    MER:KV 50 -> MER KV 50
    MER KV 50 -> MER KV 50
    """
    value = _one_line(value)
    value = value.replace(":", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _add_days(date_str: str, days: int) -> str:
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return (dt + timedelta(days=days)).strftime("%d.%m.%Y")
    except Exception:
        return ""


# ------------------------------------------------------------
# Mandant / Anspruchsteller
# ------------------------------------------------------------

def _extract_claimant(beteiligte_page: str, full: str) -> Dict[str, str]:
    """
    Extrahiert Anspruchsteller sauber aus der Beteiligten-Seite.

    Beispiel aus deinem Gutachten:
    Name Kraftverkehr Leipzig GmbH
    Herr Berthold Richter
    Straße An der Autobahn 1b
    PLZ Ort 06184 Kabelsketal
    Anspruchsteller
    Vorsteuerabzug Ja - DE453924733
    """

    data: Dict[str, str] = {}

    lines = _lines(beteiligte_page)

    idx_name = -1
    for i, line in enumerate(lines):
        if line.lower().startswith("name "):
            idx_name = i
            break

    # Ende Anspruchstellerblock: vor Kanzlei/Anwalt/Unfall
    stop = len(lines)
    for i in range(idx_name + 1 if idx_name >= 0 else 0, len(lines)):
        low = lines[i].lower()
        if low.startswith("kanzlei ") or low == "anwalt" or low.startswith("unfall "):
            stop = i
            break

    firma = ""
    anrede = ""
    person = ""
    strasse = ""
    plz_ort = ""
    vorsteuer_raw = ""

    if idx_name >= 0:
        firma = _find_line_value(lines, "Name ", idx_name, stop)

        # Zeile direkt nach Name ist oft: Herr Berthold Richter
        if idx_name + 1 < len(lines):
            person_line = lines[idx_name + 1]
            m = re.match(r"^(Herrn?|Frau)\s+(.+)$", person_line, flags=re.I)
            if m:
                anrede = _normalize_anrede(m.group(1))
                person = _one_line(m.group(2))

        strasse = _find_line_value(lines, "Straße ", idx_name, stop)
        plz_ort = _find_line_value(lines, "PLZ Ort ", idx_name, stop)
        vorsteuer_raw = _find_line_value(lines, "Vorsteuerabzug ", idx_name, stop)

    # Fallback, falls Textreihenfolge mal anders ist
    if not firma:
        firma = _search_first(
            full,
            [
                r"Beteiligte,\s*Besichtigungen\s*&\s*Auftrag.*?Name\s+(.+?)\n(?:Herr|Herrn|Frau|Straße)",
                r"Anspruchsteller\s+Name\s+(.+?)\n",
            ],
        )

    if not person:
        person_line = _search_first(
            full,
            [
                r"Name\s+" + re.escape(firma) + r"\s*\n(Herrn?\s+.+?)\n",
                r"Anspruchsteller\s+" + re.escape(firma) + r"\s*\n(.+?)\n",
            ],
        )
        m = re.match(r"^(Herrn?|Frau)\s+(.+)$", person_line, flags=re.I)
        if m:
            anrede = _normalize_anrede(m.group(1))
            person = _one_line(m.group(2))
        else:
            person = _one_line(person_line)

    vorname, nachname = _split_person(person)

    # Vorsteuer ja/nein
    vorsteuer_clean = _one_line(vorsteuer_raw)
    if re.search(r"\bja\b", vorsteuer_clean, flags=re.I):
        vorsteuer = "Ja"
    elif re.search(r"\bnein\b", vorsteuer_clean, flags=re.I):
        vorsteuer = "Nein"
    else:
        vorsteuer = ""

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_FIRMA"] = _one_line(firma)
    data["MANDANT_NAME"] = _one_line(firma) or _one_line(person)
    data["MANDANT_VORNAME"] = vorname
    data["MANDANT_NACHNAME"] = nachname
    data["MANDANT_TITEL"] = ""

    if firma and person:
        data["MANDANT_VOLLNAME"] = f"{_one_line(firma)}\n{anrede} {_one_line(person)}".strip()
    else:
        data["MANDANT_VOLLNAME"] = _one_line(firma or person)

    data["MANDANT_STRASSE"] = _one_line(strasse)
    data["MANDANT_PLZ_ORT"] = _one_line(plz_ort)

    data["VORSTEUERABZUG_RAW"] = vorsteuer_clean
    data["VORSTEUERBERECHTIGUNG"] = vorsteuer

    # Praktische Platzhalter für Anschreiben
    if anrede == "Herr" and nachname:
        data["GENDERN1"] = f"Sehr geehrter Herr {nachname},"
        data["GENDERN2"] = f"Herrn {person}".strip()
        data["GENDER1"] = "Herr"
        data["GENDER2"] = "Herrn"
        data["GENDERN"] = f"Herr {nachname}"
    elif anrede == "Frau" and nachname:
        data["GENDERN1"] = f"Sehr geehrte Frau {nachname},"
        data["GENDERN2"] = f"Frau {person}".strip()
        data["GENDER1"] = "Frau"
        data["GENDER2"] = "Frau"
        data["GENDERN"] = f"Frau {nachname}"
    else:
        data["GENDERN1"] = ""
        data["GENDERN2"] = ""
        data["GENDER1"] = ""
        data["GENDER2"] = ""
        data["GENDERN"] = ""

    return data


# ------------------------------------------------------------
# Hauptparser
# ------------------------------------------------------------

def parse_nfz_standard(pages, pdf_source=None) -> Dict[str, Any]:
    """
    NFZ Standard Parser für Reparaturschaden-Gutachten.

    Wichtig:
    - Mandant wird aus Beteiligten-Seite gelesen, nicht aus Rechnung.
    - Reparaturkosten werden netto/brutto getrennt gelesen.
    - Bei Vorsteuerabzug Ja wird standardmäßig netto verwendet.
    - Totalschaden-Felder bleiben bei Reparaturschaden leer.
    """

    pages = list(pages or [])
    full = "\n".join(pages)

    # Gezielte Seiten suchen
    invoice_page = _get_page(pages, "Rechnung Nr.", "Gesamtbetrag ohne MwSt")
    summary_page = _get_page(pages, "Zusammenfassung", "Reparaturkosten")
    beteiligte_page = _get_page(pages, "Beteiligte", "Vorsteuerabzug")
    vehicle_page = _get_page(pages, "Fahrzeugdaten", "Amtliches Kennzeichen")
    beurteilung_page = _get_page(pages, "Beurteilung", "Schadenklasse")

    data: Dict[str, Any] = {
        "_PARSER": "nfz_standard",
        "_PARSER_VARIANTE": "reparaturschaden",
        "_OK": True,
        "_WARNINGS": "",

        # Mandant
        "MANDANT_ANREDE": "",
        "MANDANT_FIRMA": "",
        "MANDANT_NAME": "",
        "MANDANT_VORNAME": "",
        "MANDANT_NACHNAME": "",
        "MANDANT_TITEL": "",
        "MANDANT_VOLLNAME": "",
        "MANDANT_STRASSE": "",
        "MANDANT_PLZ_ORT": "",

        # Gender / Anschreiben
        "GENDERN1": "",
        "GENDERN2": "",
        "GENDER1": "",
        "GENDER2": "",
        "GENDERN": "",

        # Fahrzeug / Schaden
        "AKTENZEICHEN": "",
        "RECHNUNGSNUMMER": "",
        "KENNZEICHEN": "",
        "KENNZEICHEN_MANDANT": "",
        "EIGENES_KENNZEICHEN": "",
        "KENNZEICHEN_GEGNER": "",
        "FAHRZEUGTYP": "",
        "HERSTELLER": "",
        "MODELL": "",
        "VIN": "",

        # Beteiligte / Versicherung / Gegner
        "VRSICHERUNG": "",
        "VERSICHERUNG": "",
        "UNFALLGEGNER_NAME": "",
        "SCHADENSNUMMER": "",

        # Daten
        "UNFALL_DATUM": "",
        "UNFALL_UHRZEIT": "",
        "UNFALL_ORT": "",
        "AUFTRAG_DATUM": "",
        "GUTACHTEN_DATUM": "",
        "HEUTDATUM": "",
        "HEUTEDATUM": "",
        "FRIST_DATUM": "",
        "FIRST_DATUM": "",

        # Steuer
        "VORSTEUERABZUG_RAW": "",
        "VORSTEUERBERECHTIGUNG": "",

        # Schadenhöhe
        "REPARATURSCHADEN": "",
        "REPARATURKOSTEN": "",
        "REPARATURKOSTEN_NETTO": "",
        "REPARATURKOSTEN_BRUTTO": "",
        "SCHADENHOEHE_NETTO": "",
        "SCHADENHOEHE_BRUTTO": "",

        # Fahrzeugwert / Totalschaden
        "WBW": "",
        "RESTWERT": "",
        "WIEDERBESCHAFFUNGSWERTAUFWAND": "",

        # Weitere Forderungspositionen
        "GUTACHTERKOSTEN": "",
        "GUTACHTERKOSTEN_NETTO": "",
        "GUTACHTERKOSTEN_BRUTTO": "",
        "WERTMINDERUNG": "0,00 €",
        "WERTVERBESSERUNG": "",
        "KOSTENPAUSCHALE": "25,00 €",
        "MELDUNGSKOSTEN": "",

        "ZUSATZKOSTEN_BEZEICHNUNG1": "",
        "ZUSATZKOSTEN_BETRAG1": "",
        "ZUSATZKOSTEN_BEZEICHNUNG2": "",
        "ZUSATZKOSTEN_BETRAG2": "",
        "ZUSATZKOSTEN_BEZEICHNUNG3": "",
        "ZUSATZKOSTEN_BETRAG3": "",

        # Summen
        "KOSTENSUMME_REPARATUR": "",
        "KOSTENSUMME_TOTALSCHADEN": "",
        "KOSTENSUMME_X": "",

        # Kompatibilität mit alten Platzhaltern
        "WERTVERBESSERUNG_NAME": "",
        "WERTBESSERUNG_BETRAG": "",
        "WERTMINDERUNG_NAME": "",
        "WERTMINDERUNG_BETRAG": "",
    }

    warnings: List[str] = []

    # --------------------------------------------------------
    # Mandant / Anspruchsteller
    # --------------------------------------------------------
    claimant_data = _extract_claimant(beteiligte_page, full)
    data.update(claimant_data)

    # --------------------------------------------------------
    # Aktenzeichen / Rechnungsnummer
    # --------------------------------------------------------
    data["AKTENZEICHEN"] = _search_first(
        full,
        [
            r"Aktenzeichen\s*\n?\s*(NFZ-\d{6}-\d+)",
            r"Auftragsnummer\s+(NFZ-\d{6}-\d+)",
            r"Rechnung\s+Nr\.\s*(NFZ-\d{6}-\d+)",
        ],
    )

    data["RECHNUNGSNUMMER"] = _search_first(
        invoice_page or full,
        [
            r"Rechnung\s+Nr\.\s*(NFZ-\d{6}-\d+)",
        ],
    ) or data["AKTENZEICHEN"]

    # --------------------------------------------------------
    # Datum / Frist
    # --------------------------------------------------------
    data["GUTACHTEN_DATUM"] = _search_first(
        full,
        [
            r"Halle\s*\(Saale\),\s*(\d{2}\.\d{2}\.\d{4})",
            r"Datum\s*\n?\s*(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    data["AUFTRAG_DATUM"] = _search_first(
        full,
        [
            r"Auftrag\s+vom\s+(\d{2}\.\d{2}\.\d{4})",
            r"Auftrag\s+Datum\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    # Falls dein Hauptprogramm HEUTDATUM später überschreibt, ist das okay.
    today = datetime.now().strftime("%d.%m.%Y")
    data["HEUTDATUM"] = today
    data["HEUTEDATUM"] = today
    data["FRIST_DATUM"] = _add_days(today, 14)
    data["FIRST_DATUM"] = data["FRIST_DATUM"]

    # --------------------------------------------------------
    # Unfall
    # --------------------------------------------------------
    data["UNFALL_DATUM"] = _search_first(
        beteiligte_page or full,
        [
            r"Unfall\s+Datum\s+(\d{2}\.\d{2}\.\d{4})",
            r"Unfalldatum\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    data["UNFALL_UHRZEIT"] = _search_first(
        beteiligte_page or full,
        [
            r"Uhrzeit\s+(\d{1,2}:\d{2}\s*Uhr)",
        ],
    )

    data["UNFALL_ORT"] = _one_line(
        _search_first(
            beteiligte_page or full,
            [
                r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\nUhrzeit\s+[^\n]+\nOrt\s+(.+?)(?:\nDatum|\nBesichtigung)",
                r"Uhrzeit\s+[^\n]+\nOrt\s+(.+?)(?:\nDatum|\nBesichtigung)",
            ],
        )
    )

    # --------------------------------------------------------
    # Fahrzeugdaten
    # --------------------------------------------------------
    kennzeichen = _search_first(
        vehicle_page or full,
        [
            r"Amtliches\s+Kennzeichen\s+([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,2}\s*\d{1,4})",
            r"Kennzeichen\s+([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,2}\s*\d{1,4})",
            r"\b([A-ZÄÖÜ]{1,3}[: ]+[A-Z]{1,2}\s*\d{1,4})\b",
        ],
    )
    kennzeichen = _normalize_plate(kennzeichen)

    data["KENNZEICHEN"] = kennzeichen
    data["KENNZEICHEN_MANDANT"] = kennzeichen
    data["EIGENES_KENNZEICHEN"] = kennzeichen

    hersteller = _search_first(
        vehicle_page or full,
        [
            r"Hersteller\s+(.+?)\n",
        ],
    )

    modell = _search_first(
        vehicle_page or full,
        [
            r"Modell/Haupttyp\s+(.+?)\n",
            r"Modell\s*\n?\s+(.+?)\n(?:Anspruchsteller|Sachverständiger|Amtliches|Untertyp)",
        ],
    )

    data["HERSTELLER"] = _one_line(hersteller)
    data["MODELL"] = _one_line(modell)

    if hersteller and modell:
        data["FAHRZEUGTYP"] = f"{_one_line(hersteller)} {_one_line(modell)}"
    else:
        data["FAHRZEUGTYP"] = _one_line(
            _search_first(
                invoice_page or full,
                [
                    r"Fahrzeug\s+(.+?)\nKennzeichen",
                ],
            )
        )

    data["VIN"] = _search_first(
        vehicle_page or invoice_page or full,
        [
            r"Fahrzeugidentifikationsnummer\s*\(VIN\)\s+([A-HJ-NPR-Z0-9]{10,20})",
            r"VIN[:\s]+([A-HJ-NPR-Z0-9]{10,20})",
            r"Versicherter\s+.+?\s+VIN\s+([A-HJ-NPR-Z0-9]{10,20})",
        ],
    )

    # --------------------------------------------------------
    # Unfallgegner / Versicherter
    # --------------------------------------------------------
    gegner = _search_first(
        beteiligte_page or invoice_page or full,
        [
            r"Unfallgegner\s+Name\s+(.+?)\n",
            r"Versicherter\s+(.+?)\s+VIN",
        ],
    )

    data["UNFALLGEGNER_NAME"] = _one_line(gegner)
    data["VERSICHERUNG"] = _one_line(gegner)
    data["VRSICHERUNG"] = _one_line(gegner)

    # Falls irgendwann eine echte Schadennummer vorhanden ist
    data["SCHADENSNUMMER"] = _search_first(
        full,
        [
            r"Schadennummer\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-\/]{5,40})",
            r"Schaden-?Nr\.\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-\/]{5,40})",
        ],
    )

    # --------------------------------------------------------
    # Reparaturschaden erkennen
    # --------------------------------------------------------
    if re.search(r"Es\s+handelt\s+sich\s+um\s+einen\s+Reparaturschaden", full, flags=re.I):
        data["REPARATURSCHADEN"] = "Ja"
    elif re.search(r"Schadenklasse\s*:\s*Reparaturschaden", full, flags=re.I):
        data["REPARATURSCHADEN"] = "Ja"
    elif re.search(r"\bReparaturschaden\b", full, flags=re.I):
        data["REPARATURSCHADEN"] = "Ja"
    else:
        data["REPARATURSCHADEN"] = ""

    # --------------------------------------------------------
    # Reparaturkosten / Schadenhöhe
    # --------------------------------------------------------
    rep_netto = _extract_money(
        summary_page + "\n" + full,
        [
            r"Reparaturkosten\s+ohne\s+MwSt\.\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Reparaturkosten\s+netto\s*([0-9][0-9\.\, ]*)",
        ],
    )

    rep_brutto = _extract_money(
        summary_page + "\n" + full,
        [
            r"Reparaturkosten\s+inkl\.\s+MwSt\.\s*\([^)]+\)\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Reparaturkosten\s+brutto\s*([0-9][0-9\.\, ]*)",
            r"Schadenhöhe\s+inkl\.\s+MwSt\.\s*\([^)]+\)\s*([0-9][0-9\.\, ]*)\s*€?",
        ],
    )

    data["REPARATURKOSTEN_NETTO"] = rep_netto
    data["REPARATURKOSTEN_BRUTTO"] = rep_brutto
    data["SCHADENHOEHE_NETTO"] = rep_netto
    data["SCHADENHOEHE_BRUTTO"] = rep_brutto

    # --------------------------------------------------------
    # WBW / Restwert
    # --------------------------------------------------------
    data["WBW"] = _extract_money(
        summary_page + "\n" + full,
        [
            r"Wiederbeschaffungswert\s*\(steuerneutral\)\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Wiederbeschaffungswert\s*:\s*([0-9][0-9\.\, ]*)\s*€?",
            r"\bWiederbeschaffungswert\s+([0-9][0-9\.\, ]*)\s*€",
        ],
    )

    # Bei diesem Standard-Reparaturschaden: kein Restwert
    if re.search(r"Restwertermittlung\s*\(keine\)", full, flags=re.I):
        data["RESTWERT"] = ""
    else:
        data["RESTWERT"] = _extract_money(
            full,
            [
                r"Restwert\s*[:\-]?\s*([0-9][0-9\.\, ]*)\s*€",
                r"Restwertermittlung.*?([0-9][0-9\.\, ]*)\s*€",
            ],
        )

    # --------------------------------------------------------
    # Wertminderung
    # --------------------------------------------------------
    if re.search(r"Merkantiler\s+Minderwert\s*\(keiner\)", full, flags=re.I):
        data["WERTMINDERUNG"] = "0,00 €"
        data["WERTMINDERUNG_NAME"] = "Merkantiler Minderwert"
        data["WERTMINDERUNG_BETRAG"] = "0,00 €"
    else:
        minderwert = _extract_money(
            full,
            [
                r"Merkantiler\s+Minderwert\s*[:\-]?\s*([0-9][0-9\.\, ]*)\s*€",
                r"Wertminderung\s*[:\-]?\s*([0-9][0-9\.\, ]*)\s*€",
            ],
        )
        data["WERTMINDERUNG"] = minderwert or "0,00 €"
        data["WERTMINDERUNG_NAME"] = "Merkantiler Minderwert" if minderwert else ""
        data["WERTMINDERUNG_BETRAG"] = minderwert or "0,00 €"

    # --------------------------------------------------------
    # Gutachterkosten aus Rechnung
    # --------------------------------------------------------
    gutachter_netto = _extract_money(
        invoice_page or full,
        [
            r"Gesamtbetrag\s+ohne\s+MwSt\.\s*([0-9][0-9\.\, ]*)\s*€?",
        ],
    )

    gutachter_brutto = _extract_money(
        invoice_page or full,
        [
            r"Gesamtbetrag\s+inkl\.\s+MwSt\.\s*([0-9][0-9\.\, ]*)\s*€?",
        ],
    )

    data["GUTACHTERKOSTEN_NETTO"] = gutachter_netto
    data["GUTACHTERKOSTEN_BRUTTO"] = gutachter_brutto

    # --------------------------------------------------------
    # Netto/Brutto-Logik bei Vorsteuer
    # --------------------------------------------------------
    vorsteuer_ja = data.get("VORSTEUERBERECHTIGUNG") == "Ja"

    if vorsteuer_ja:
        data["REPARATURKOSTEN"] = rep_netto or rep_brutto
        data["GUTACHTERKOSTEN"] = gutachter_netto or gutachter_brutto
    else:
        data["REPARATURKOSTEN"] = rep_brutto or rep_netto
        data["GUTACHTERKOSTEN"] = gutachter_brutto or gutachter_netto

    # --------------------------------------------------------
    # Summenlogik Reparaturschaden
    # --------------------------------------------------------
    # Reparaturschaden:
    # Reparaturkosten + Gutachterkosten + Wertminderung + Kostenpauschale + Zusatzkosten
    # Bei Vorsteuerabzug Ja werden Netto-Werte verwendet.
    if data["REPARATURKOSTEN"] or data["GUTACHTERKOSTEN"]:
        data["KOSTENSUMME_REPARATUR"] = _sum_eur(
            data["REPARATURKOSTEN"],
            data["GUTACHTERKOSTEN"],
            data["WERTMINDERUNG"],
            data["KOSTENPAUSCHALE"],
            data["MELDUNGSKOSTEN"],
            data["ZUSATZKOSTEN_BETRAG1"],
            data["ZUSATZKOSTEN_BETRAG2"],
            data["ZUSATZKOSTEN_BETRAG3"],
        )
    else:
        data["KOSTENSUMME_REPARATUR"] = ""

    data["KOSTENSUMME_X"] = data["KOSTENSUMME_REPARATUR"]

    # Bei Reparaturschaden bewusst leer lassen
    data["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""
    data["KOSTENSUMME_TOTALSCHADEN"] = ""

    # --------------------------------------------------------
    # Plausibilitätsprüfung / Warnungen
    # --------------------------------------------------------
    required = {
        "MANDANT_NAME": data["MANDANT_NAME"],
        "AKTENZEICHEN": data["AKTENZEICHEN"],
        "KENNZEICHEN": data["KENNZEICHEN"],
        "REPARATURKOSTEN": data["REPARATURKOSTEN"],
        "WBW": data["WBW"],
    }

    for key, value in required.items():
        if not value:
            warnings.append(f"{key} nicht gefunden")

    if warnings:
        data["_OK"] = False
        data["_WARNINGS"] = "; ".join(warnings)
    else:
        data["_OK"] = True
        data["_WARNINGS"] = ""

    return data
