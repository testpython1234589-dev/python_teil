from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta
import re

import gutachten_extractor as gx


# ============================================================
# nfz_standard.py
# NFZ Standard Parser – Reparaturschaden
#
# Drop-in-Ersatz für deine alte Datei:
# def parse_nfz_standard(pages, pdf_source=None) -> Dict[str, Any]
#
# Wichtig:
# - Michael Hohlwein wird NICHT als Mandant genommen.
# - Mandant wird aus dem Anspruchsteller-Block gelesen.
# - Rechtsanwalt/Kanzlei wird getrennt ignoriert.
# - Reparaturschaden != Totalschaden.
# ============================================================


# ------------------------------------------------------------
# Basis-Helfer
# ------------------------------------------------------------

def _clean(value: str) -> str:
    return (value or "").replace("\xa0", " ").strip()


def _one_line(value: str) -> str:
    return " ".join(_clean(value).split())


def _lines(text: str) -> List[str]:
    return [_clean(x) for x in (text or "").splitlines() if _clean(x)]


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
    """Gibt die erste Seite zurück, die alle Keywords enthält."""
    for page in pages:
        low = (page or "").lower()
        if all(k.lower() in low for k in keywords):
            return page
    return ""


def _cut_before(text: str, patterns: List[str]) -> str:
    """
    Schneidet Text vor dem frühesten Pattern ab.
    Dadurch wird der Kanzlei-/Anwaltblock sicher entfernt.
    """
    if not text:
        return ""

    cut_positions = []
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            cut_positions.append(m.start())

    if not cut_positions:
        return text

    return text[:min(cut_positions)]


def _value_after_label(block: str, label: str) -> str:
    """
    Robust für beide Varianten:
    1) Straße An der Autobahn 1b
    2) Straße
       An der Autobahn 1b
    """
    lines = _lines(block)
    label_low = label.lower()

    for i, line in enumerate(lines):
        low = line.lower()

        # Variante: "Straße An der Autobahn 1b"
        if low.startswith(label_low + " "):
            return _one_line(line[len(label):])

        # Variante: "Straße" in eigener Zeile
        if low == label_low and i + 1 < len(lines):
            return _one_line(lines[i + 1])

    return ""


def _parse_eur(value: str) -> Optional[Decimal]:
    """Deutsche Geldwerte -> Decimal."""
    if not value:
        return None

    s = str(value)
    s = s.replace("€", "").replace("\xa0", " ").strip()
    s = re.sub(r"[^0-9,.\-]", "", s)

    if not s:
        return None

    # 1.063,00 -> 1063.00
    if "," in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    else:
        # 7.900 -> 7900
        if re.search(r"\.\d{3}$", s):
            s = s.replace(".", "")

    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _format_eur(value: Decimal | str | int | float | None) -> str:
    if value is None:
        return ""

    if not isinstance(value, Decimal):
        value = _parse_eur(str(value))
        if value is None:
            return ""

    value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{value:,.2f}"       # 1,063.00
    s = s.replace(",", "X")   # 1X063.00
    s = s.replace(".", ",")   # 1X063,00
    s = s.replace("X", ".")   # 1.063,00
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


def _split_person(person: str) -> Tuple[str, str]:
    person = _one_line(person)
    if not person:
        return "", ""

    parts = person.split()
    if len(parts) == 1:
        return "", parts[0]

    return " ".join(parts[:-1]), parts[-1]


def _normalize_anrede(value: str) -> str:
    v = _one_line(value).lower()

    if v in {"herr", "herrn"}:
        return "Herr"
    if v == "frau":
        return "Frau"

    return ""


def _normalize_plate(value: str) -> str:
    value = _one_line(value)
    value = value.replace(":", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value



def _extract_unfallgegner_nfz_standard(beteiligte_page: str) -> Dict[str, str]:
    """
    Extrahiert Unfallgegner aus dem Block:

    Unfallgegner
    Name ...
    Straße ...
    PLZ Ort ...

    Funktioniert auch bei PDF-Text wie:
    Unfallgegner Name
    Poco Einrichtungsmärkte
    Straße
    Naumburger Str. 16-22
    PLZ Ort
    04229 Leipzig
    """
    result = {
        "UNFALLGEGNER_NAME": "",
        "UNFALLGEGNER_STRASSE": "",
        "UNFALLGEGNER_PLZ_ORT": "",
    }

    if not beteiligte_page:
        return result

    lines = _lines(beteiligte_page)

    block_lines = []
    in_block = False

    for line in lines:
        low = line.lower().strip()

        # Start Unfallgegner-Block
        if low.startswith("unfallgegner"):
            in_block = True

            # WICHTIG:
            # Bei "Unfallgegner Name" darf "Name" nicht verloren gehen.
            rest = re.sub(r"^unfallgegner\s*", "", line, flags=re.I).strip()
            if rest:
                block_lines.append(rest)

            continue

        if in_block:
            # Ende Unfallgegner-Block
            if (
                low.startswith("auftrag")
                or low.startswith("datum ")
                or low.startswith("erteilt durch")
                or low.startswith("beauftragung")
                or low.startswith("gemäß auftrag")
                or low.startswith("anwalt")
                or low.startswith("besichtigung")
                or low.startswith("unfall datum")
            ):
                break

            block_lines.append(line)

    block = "\n".join(block_lines)

    name = _one_line(_value_after_label(block, "Name"))
    strasse = _one_line(_value_after_label(block, "Straße"))
    plz_ort = _one_line(_value_after_label(block, "PLZ Ort"))

    # Fallback, falls Label "Name" trotzdem nicht erkannt wurde:
    # Erste freie Zeile vor Straße/PLZ ist sehr wahrscheinlich der Name.
    if not name:
        for line in block_lines:
            cleaned = _one_line(line)
            low = cleaned.lower()

            if not cleaned:
                continue

            if low in {"name", "straße", "strasse", "plz ort", "plz/ort"}:
                continue

            if low.startswith("straße ") or low.startswith("strasse "):
                continue

            if low.startswith("plz ort ") or low.startswith("plz/ort "):
                continue

            if re.match(r"^\d{5}\s+", cleaned):
                continue

            # Das ist dann "Poco Einrichtungsmärkte"
            name = cleaned
            break

    result["UNFALLGEGNER_NAME"] = name
    result["UNFALLGEGNER_STRASSE"] = strasse
    result["UNFALLGEGNER_PLZ_ORT"] = plz_ort

    return result

    lines = _lines(beteiligte_page)

    block_lines = []
    in_block = False

    for line in lines:
        low = line.lower()

        # Start Unfallgegner-Block
        if low.startswith("unfallgegner"):
            in_block = True

            # Wichtig:
            # Falls die Zeile "Unfallgegner Name" lautet,
            # darf "Name" nicht verloren gehen.
            rest = re.sub(r"^unfallgegner\s*", "", line, flags=re.I).strip()
            if rest:
                block_lines.append(rest)

            continue

        if in_block:
            # Ende Unfallgegner-Block
            if (
                low.startswith("auftrag")
                or low.startswith("datum ")
                or low.startswith("erteilt durch")
                or low.startswith("beauftragung")
                or low.startswith("gemäß auftrag")
                or low.startswith("anwalt")
                or low.startswith("besichtigung")
                or low.startswith("unfall datum")
            ):
                break

            block_lines.append(line)

    block = "\n".join(block_lines)

    name = _one_line(_value_after_label(block, "Name"))
    strasse = _one_line(_value_after_label(block, "Straße"))
    plz_ort = _one_line(_value_after_label(block, "PLZ Ort"))

    # Fallback:
    # Wenn "Name" als Label verloren ging, ist oft die erste freie Zeile der Name.
    if not name:
        for line in block_lines:
            low = line.lower().strip()

            if low in {"name", "straße", "strasse", "plz ort", "plz/ort"}:
                continue

            if low.startswith("straße ") or low.startswith("strasse "):
                continue

            if low.startswith("plz ort ") or low.startswith("plz/ort "):
                continue

            if re.match(r"^\d{5}\s+", line):
                continue

            # Erste echte freie Zeile ist sehr wahrscheinlich der Name
            name = _one_line(line)
            break

    result["UNFALLGEGNER_NAME"] = name
    result["UNFALLGEGNER_STRASSE"] = strasse
    result["UNFALLGEGNER_PLZ_ORT"] = plz_ort

    return result


def _extract_unfallgegner_nfz_standard(beteiligte_page: str) -> Dict[str, str]:
    """
    Extrahiert Unfallgegner aus dem Block:

    Unfallgegner
    Name ...
    Straße ...
    PLZ Ort ...
    """
    result = {
        "UNFALLGEGNER_NAME": "",
        "UNFALLGEGNER_STRASSE": "",
        "UNFALLGEGNER_PLZ_ORT": "",
    }

    if not beteiligte_page:
        return result

    lines = _lines(beteiligte_page)

    block_lines = []
    in_block = False

    for line in lines:
        low = line.lower()

        if low.startswith("unfallgegner"):
            in_block = True
            continue

        if in_block:
            # Ende Unfallgegner-Block
            if (
                low.startswith("auftrag")
                or low.startswith("datum ")
                or low.startswith("erteilt durch")
                or low.startswith("beauftragung")
                or low.startswith("gemäß auftrag")
                or low.startswith("anwalt")
                or low.startswith("besichtigung")
            ):
                break

            block_lines.append(line)

    block = "\n".join(block_lines)

    result["UNFALLGEGNER_NAME"] = _one_line(_value_after_label(block, "Name"))
    result["UNFALLGEGNER_STRASSE"] = _one_line(_value_after_label(block, "Straße"))
    result["UNFALLGEGNER_PLZ_ORT"] = _one_line(_value_after_label(block, "PLZ Ort"))

    return result


def _add_days(date_str: str, days: int) -> str:
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return (dt + timedelta(days=days)).strftime("%d.%m.%Y")
    except Exception:
        return ""


# ------------------------------------------------------------
# Anspruchsteller/Mandant
# ------------------------------------------------------------

def _extract_claimant_from_beteiligte_page(beteiligte_page: str) -> Dict[str, str]:
    """
    Liest NUR den Anspruchstellerblock.

    Fehlerursache bei dir:
    Die Seite enthält danach auch:
    Kanzlei Rechtsanwalt Michael Hohlwein
    Name Michael Hohlwein
    ...
    Wenn man einfach "Name ..." sucht, kann fälschlich Michael Hohlwein kommen.

    Lösung:
    Vor "Kanzlei", "Anwalt" oder "Unfall Datum" abschneiden.
    """

    result = {
        "MANDANT_ANREDE": "",
        "MANDANT_FIRMA": "",
        "MANDANT_NAME": "",
        "MANDANT_VORNAME": "",
        "MANDANT_NACHNAME": "",
        "MANDANT_TITEL": "",
        "MANDANT_VOLLNAME": "",
        "MANDANT_STRASSE": "",
        "MANDANT_PLZ_ORT": "",
        "VORSTEUERABZUG_RAW": "",
        "VORSTEUERBERECHTIGUNG": "",
        "GENDERN1": "",
        "GENDERN2": "",
        "GENDER1": "",
        "GENDER2": "",
        "GENDERN": "",
    }

    if not beteiligte_page:
        return result

    # Kanzlei-/Anwaltsblock komplett entfernen
    claimant_block = _cut_before(
        beteiligte_page,
        [
            r"\n\s*Kanzlei\b",
            r"\n\s*Anwalt\b",
            r"\bKanzlei\s+Rechtsanwalt\b",
            r"\n\s*Unfall\s+Datum\b",
        ],
    )

    # Header entfernen, falls vorhanden
    claimant_block = re.sub(
        r"^.*?Beteiligte,\s*Besichtigungen\s*&\s*Auftrag",
        "",
        claimant_block,
        flags=re.S | re.I,
    )

    firma = _value_after_label(claimant_block, "Name")

    # Falls PDF-Text in einer Zeile steht:
    if not firma:
        firma = _search_first(
            claimant_block,
            [
                r"Name\s+(.+?)(?:\n|Herrn?\s|Frau\s|Straße\s|PLZ\s*Ort\s|Vorsteuerabzug\s)",
            ],
        )

    # Person: Herr/Frau innerhalb des bereits gekürzten Anspruchstellerblocks
    anrede = ""
    person = ""

    person_line = _search_first(
        claimant_block,
        [
            r"\b(Herrn?\s+[A-ZÄÖÜ][^\n]+)",
            r"\b(Frau\s+[A-ZÄÖÜ][^\n]+)",
        ],
    )

    m = re.match(r"^(Herrn?|Frau)\s+(.+)$", _one_line(person_line), flags=re.I)
    if m:
        anrede = _normalize_anrede(m.group(1))
        person = _one_line(m.group(2))

    strasse = _value_after_label(claimant_block, "Straße")
    plz_ort = _value_after_label(claimant_block, "PLZ Ort")
    vorsteuer_raw = _value_after_label(claimant_block, "Vorsteuerabzug")

    # Vorsteuer manchmal nach "Anspruchsteller" in gleicher Zeile
    if not vorsteuer_raw:
        vorsteuer_raw = _search_first(
            claimant_block,
            [
                r"Vorsteuerabzug\s+(.+?)(?:\n|$)",
            ],
        )

    vorsteuer_raw = _one_line(vorsteuer_raw)

    if re.search(r"\bja\b", vorsteuer_raw, flags=re.I):
        vorsteuer = "Ja"
    elif re.search(r"\bnein\b", vorsteuer_raw, flags=re.I):
        vorsteuer = "Nein"
    else:
        vorsteuer = ""

    vorname, nachname = _split_person(person)
        # Ansprechpartner separat speichern
    result["ANSPRECHPARTNER_ANREDE"] = anrede
    result["ANSPRECHPARTNER_NAME"] = person
    result["ANSPRECHPARTNER_VORNAME"] = vorname
    result["ANSPRECHPARTNER_NACHNAME"] = nachname

    firma = _one_line(firma)

    result["MANDANT_ANREDE"] = anrede
    result["MANDANT_FIRMA"] = firma
    result["MANDANT_NAME"] = firma or person
    result["MANDANT_VORNAME"] = vorname
    result["MANDANT_NACHNAME"] = nachname
    result["MANDANT_STRASSE"] = _one_line(strasse)
    result["MANDANT_PLZ_ORT"] = _one_line(plz_ort)
    result["VORSTEUERABZUG_RAW"] = vorsteuer_raw
    result["VORSTEUERBERECHTIGUNG"] = vorsteuer

    if firma and person:
        result["MANDANT_VOLLNAME"] = f"{firma}\n{anrede} {person}".strip()
    else:
        result["MANDANT_VOLLNAME"] = firma or person

    # Anschreiben-Gender
    if anrede == "Herr" and nachname:
        result["GENDERN1"] = f"Sehr geehrter Herr {nachname},"
        result["GENDERN2"] = f"Herrn {person}"
        result["GENDER1"] = "Herr"
        result["GENDER2"] = "Herrn"
        result["GENDERN"] = f"Herr {nachname}"
    elif anrede == "Frau" and nachname:
        result["GENDERN1"] = f"Sehr geehrte Frau {nachname},"
        result["GENDERN2"] = f"Frau {person}"
        result["GENDER1"] = "Frau"
        result["GENDER2"] = "Frau"
        result["GENDERN"] = f"Frau {nachname}"

    return result


def _extract_claimant_from_invoice(invoice_page: str) -> Dict[str, str]:
    """
    Fallback, falls Beteiligten-Seite nicht gelesen werden kann.
    Liest Adresse oben aus der Rechnung.
    """
    result = {
        "MANDANT_ANREDE": "",
        "MANDANT_FIRMA": "",
        "MANDANT_NAME": "",
        "MANDANT_VORNAME": "",
        "MANDANT_NACHNAME": "",
        "MANDANT_TITEL": "",
        "MANDANT_VOLLNAME": "",
        "MANDANT_STRASSE": "",
        "MANDANT_PLZ_ORT": "",
        "VORSTEUERABZUG_RAW": "",
        "VORSTEUERBERECHTIGUNG": "",
        "GENDERN1": "",
        "GENDERN2": "",
        "GENDER1": "",
        "GENDER2": "",
        "GENDERN": "",
    }

    if not invoice_page:
        return result

    # Bereich zwischen Absender und Rechnung Nr.
    block = _search_first(
        invoice_page,
        [
            r"Halle\s*\(Saale\)\s*\n(.+?)\nRechnung\s+Nr\.",
            r"06112\s+Halle\s*\(Saale\)\s*\n(.+?)\nRechnung\s+Nr\.",
        ],
    )

    ls = _lines(block)

    firma = ""
    anrede = ""
    person = ""
    strasse = ""
    plz_ort = ""

    if ls:
        firma = ls[0]

    for line in ls[1:]:
        m = re.match(r"^(Herrn?|Frau)\s+(.+)$", line, flags=re.I)
        if m:
            anrede = _normalize_anrede(m.group(1))
            person = _one_line(m.group(2))
            continue

        if re.match(r"^\d{5}\s+", line):
            plz_ort = line
            continue

        if not strasse:
            strasse = line

    vorname, nachname = _split_person(person)

    result["MANDANT_ANREDE"] = anrede
    result["MANDANT_FIRMA"] = _one_line(firma)
    result["MANDANT_NAME"] = _one_line(firma) or person
    result["MANDANT_VORNAME"] = vorname
    result["MANDANT_NACHNAME"] = nachname
    result["MANDANT_STRASSE"] = _one_line(strasse)
    result["MANDANT_PLZ_ORT"] = _one_line(plz_ort)

    if firma and person:
        result["MANDANT_VOLLNAME"] = f"{_one_line(firma)}\n{anrede} {person}".strip()
    else:
        result["MANDANT_VOLLNAME"] = _one_line(firma or person)

    if anrede == "Herr" and nachname:
        result["GENDERN1"] = f"Sehr geehrter Herr {nachname},"
        result["GENDERN2"] = f"Herrn {person}"
        result["GENDER1"] = "Herr"
        result["GENDER2"] = "Herrn"
        result["GENDERN"] = f"Herr {nachname}"
    elif anrede == "Frau" and nachname:
        result["GENDERN1"] = f"Sehr geehrte Frau {nachname},"
        result["GENDERN2"] = f"Frau {person}"
        result["GENDER1"] = "Frau"
        result["GENDER2"] = "Frau"
        result["GENDERN"] = f"Frau {nachname}"

    return result


# ------------------------------------------------------------
# Hauptfunktion
# ------------------------------------------------------------

def parse_nfz_standard(pages, pdf_source=None) -> Dict[str, Any]:
    pages = list(pages or [])
    full = "\n".join(pages)

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

        "MANDANT_ANREDE": "",
        "MANDANT_FIRMA": "",
        "MANDANT_NAME": "",
        "MANDANT_VORNAME": "",
        "MANDANT_NACHNAME": "",
        "MANDANT_TITEL": "",
        "MANDANT_VOLLNAME": "",
        "MANDANT_STRASSE": "",
        "MANDANT_PLZ_ORT": "",

        "GENDERN1": "",
        "GENDERN2": "",
        "GENDER1": "",
        "GENDER2": "",
        "GENDERN": "",

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

        "VRSICHERUNG": "",
        "VERSICHERUNG": "",
        "VER_STRASSE": "",
        "VER_ORT": "",
        
        "UNFALLGEGNER_NAME": "",
        "UNFALLGEGNER_STRASSE": "",
        "UNFALLGEGNER_PLZ_ORT": "",
        "ANSPRUCHSGEGNER": "",
        
        "SCHADENSNUMMER": "",

        "UNFALL_DATUM": "",
        "UNFALL_UHRZEIT": "",
        "UNFALL_ORT": "",
        "AUFTRAG_DATUM": "",
        "GUTACHTEN_DATUM": "",
        "HEUTDATUM": "",
        "HEUTEDATUM": "",
        "FRIST_DATUM": "",
        "FIRST_DATUM": "",

        "VORSTEUERABZUG_RAW": "",
        "VORSTEUERBERECHTIGUNG": "",

        "SCHADENART": "",
        "REPARATURSCHADEN": "",
        "REPARATURKOSTEN": "",
        "REPARATURKOSTEN_NETTO": "",
        "REPARATURKOSTEN_BRUTTO": "",
        "SCHADENHOEHE_NETTO": "",
        "SCHADENHOEHE_BRUTTO": "",

        "WBW": "",
        "RESTWERT": "",
        "WIEDERBESCHAFFUNGSWERTAUFWAND": "",

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

        "KOSTENSUMME_REPARATUR": "",
        "KOSTENSUMME_TOTALSCHADEN": "",
        "KOSTENSUMME_X": "",

        "WERTVERBESSERUNG_NAME": "",
        "WERTBESSERUNG_BETRAG": "",
        "WERTMINDERUNG_NAME": "",
        "WERTMINDERUNG_BETRAG": "",
    }

    warnings: List[str] = []

    # 1) Mandant: Erst Beteiligte-Seite, dann Rechnung als Fallback
    claimant = _extract_claimant_from_beteiligte_page(beteiligte_page)
    if not claimant.get("MANDANT_NAME"):
        claimant = _extract_claimant_from_invoice(invoice_page)

    data.update(claimant)

    # 2) Aktenzeichen / Rechnung
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
        [r"Rechnung\s+Nr\.\s*(NFZ-\d{6}-\d+)"],
    ) or data["AKTENZEICHEN"]

    # 3) Datum
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

    today = datetime.now().strftime("%d.%m.%Y")
    data["HEUTDATUM"] = today
    data["HEUTEDATUM"] = today
    data["FRIST_DATUM"] = _add_days(today, 14)
    data["FIRST_DATUM"] = data["FRIST_DATUM"]

    # 4) Unfall
    data["UNFALL_DATUM"] = _search_first(
        beteiligte_page or full,
        [
            r"Unfall\s+Datum\s+(\d{2}\.\d{2}\.\d{4})",
            r"Unfalldatum\s+(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    data["UNFALL_UHRZEIT"] = _search_first(
        beteiligte_page or full,
        [r"Uhrzeit\s+(\d{1,2}:\d{2}\s*Uhr)"],
    )

    # Ort kann im PDF-Zeilentext zweizeilig sein
    data["UNFALL_ORT"] = _one_line(
        _search_first(
            beteiligte_page or full,
            [
                r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\nUhrzeit\s+[^\n]+\nOrt\s+(.+?)(?:\nDatum|\nBesichtigung)",
                r"Uhrzeit\s+[^\n]+\nOrt\s+(.+?)(?:\nDatum|\nBesichtigung)",
                r"Ort\s+(Poco\s+Einrichtungsmärkte.+?)(?:\nDatum|\nBesichtigung)",
            ],
        )
    )

    # 5) Fahrzeug
    kennzeichen = _search_first(
        vehicle_page or invoice_page or full,
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

    # Wichtig: Gegnerkennzeichen nicht mit Mandantenkennzeichen befüllen!
    data["KENNZEICHEN_GEGNER"] = ""

    hersteller = _search_first(
        vehicle_page or full,
        [r"Hersteller\s+(.+?)\n"],
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

    if data["HERSTELLER"] and data["MODELL"]:
        data["FAHRZEUGTYP"] = f'{data["HERSTELLER"]} {data["MODELL"]}'
    else:
        data["FAHRZEUGTYP"] = _one_line(
            _search_first(
                invoice_page or full,
                [r"Fahrzeug\s+(.+?)\nKennzeichen"],
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

    # 6) Gegner / Versicherung
    # 6) Gegner / Versicherung

    # Unfallgegner immer separat lesen
    unfallgegner = _extract_unfallgegner_nfz_standard(beteiligte_page)
    
    data["UNFALLGEGNER_NAME"] = unfallgegner.get("UNFALLGEGNER_NAME", "")
    data["UNFALLGEGNER_STRASSE"] = unfallgegner.get("UNFALLGEGNER_STRASSE", "")
    data["UNFALLGEGNER_PLZ_ORT"] = unfallgegner.get("UNFALLGEGNER_PLZ_ORT", "")
    data["ANSPRUCHSGEGNER"] = data["UNFALLGEGNER_NAME"]
    
    # Echte Versicherung suchen
    # Wichtig: NICHT "Versicherter" verwenden, weil das bei deinem PDF Poco ist,
    # aber keine Versicherung.
    versicherung_name = _search_first(
        beteiligte_page or full,
        [
            r"Versicherung\s+Name\s+(.+?)\n",
            r"\nVersicherung\s+(.+?)\n",
        ],
    )
    
    versicherung_strasse = _search_first(
        beteiligte_page or full,
        [
            r"Versicherung\s+Name\s+.+?\nStraße\s+(.+?)\nPLZ Ort",
            r"\nVersicherung\s+.+?\nStraße\s+(.+?)\nPLZ Ort",
        ],
    )
    
    versicherung_ort = _search_first(
        beteiligte_page or full,
        [
            r"Versicherung\s+Name\s+.+?\n(?:Straße\s+.+?\n)?PLZ Ort\s+(.+?)\n",
            r"\nVersicherung\s+.+?\n(?:Straße\s+.+?\n)?PLZ Ort\s+(.+?)\n",
        ],
    )
    
    # Wenn echte Versicherung vorhanden: Versicherung verwenden
    if versicherung_name:
        data["VERSICHERUNG"] = _one_line(versicherung_name)
        data["VRSICHERUNG"] = _one_line(versicherung_name)
        data["VER_STRASSE"] = _one_line(versicherung_strasse)
        data["VER_ORT"] = _one_line(versicherung_ort)
    
    # Wenn keine Versicherung vorhanden: Unfallgegner als Ersatz verwenden
    else:
        data["VERSICHERUNG"] = data["UNFALLGEGNER_NAME"]
        data["VRSICHERUNG"] = data["UNFALLGEGNER_NAME"]
        data["VER_STRASSE"] = data["UNFALLGEGNER_STRASSE"]
        data["VER_ORT"] = data["UNFALLGEGNER_PLZ_ORT"]
    
        data["SCHADENSNUMMER"] = _search_first(
            full,
            [
                r"Schadennummer\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-\/]{5,40})",
                r"Schaden-?Nr\.\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-\/]{5,40})",
            ],
        )

    # 7) Schadenart
    if re.search(r"Es\s+handelt\s+sich\s+um\s+einen\s+Reparaturschaden", full, flags=re.I) or \
       re.search(r"Schadenklasse\s*:\s*Reparaturschaden", full, flags=re.I):
        data["SCHADENART"] = "Reparaturschaden"
        data["REPARATURSCHADEN"] = "Ja"
    else:
        data["SCHADENART"] = ""
        data["REPARATURSCHADEN"] = ""

    # 8) Reparaturkosten
    money_source = summary_page + "\n" + full

    rep_netto = _extract_money(
        money_source,
        [
            r"Reparaturkosten\s+ohne\s+MwSt\.\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Reparaturkosten\s+netto\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Reparaturkosten\s+netto\s+([0-9][0-9\.\, ]*)",
        ],
    )

    rep_brutto = _extract_money(
        money_source,
        [
            r"Reparaturkosten\s+inkl\.\s+MwSt\.\s*\([^)]+\)\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Schadenhöhe\s+inkl\.\s+MwSt\.\s*\([^)]+\)\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Reparaturkosten\s+brutto\s*([0-9][0-9\.\, ]*)\s*€?",
        ],
    )

    data["REPARATURKOSTEN_NETTO"] = rep_netto
    data["REPARATURKOSTEN_BRUTTO"] = rep_brutto
    data["SCHADENHOEHE_NETTO"] = rep_netto
    data["SCHADENHOEHE_BRUTTO"] = rep_brutto

    # 9) WBW / Restwert
    data["WBW"] = _extract_money(
        money_source,
        [
            r"Wiederbeschaffungswert\s*\(steuerneutral\)\s*([0-9][0-9\.\, ]*)\s*€?",
            r"Wiederbeschaffungswert\s*:\s*([0-9][0-9\.\, ]*)\s*€?",
            r"\bWiederbeschaffungswert\s+([0-9][0-9\.\, ]*)\s*€",
        ],
    )

    if re.search(r"Restwertermittlung\s*\(keine\)", full, flags=re.I):
        data["RESTWERT"] = ""
    else:
        data["RESTWERT"] = _extract_money(
            full,
            [
                r"Restwert\s*[:\-]?\s*([0-9][0-9\.\, ]*)\s*€",
            ],
        )

    # 10) Wertminderung
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
        data["WERTMINDERUNG_BETRAG"] = minderwert or "0,00 €"
        data["WERTMINDERUNG_NAME"] = "Merkantiler Minderwert" if minderwert else ""

    # 11) Gutachterkosten aus Rechnung
    gutachter_netto = _extract_money(
        invoice_page or full,
        [r"Gesamtbetrag\s+ohne\s+MwSt\.\s*([0-9][0-9\.\, ]*)\s*€?"],
    )

    gutachter_brutto = _extract_money(
        invoice_page or full,
        [r"Gesamtbetrag\s+inkl\.\s+MwSt\.\s*([0-9][0-9\.\, ]*)\s*€?"],
    )

    data["GUTACHTERKOSTEN_NETTO"] = gutachter_netto
    data["GUTACHTERKOSTEN_BRUTTO"] = gutachter_brutto

    # 12) Netto-/Brutto-Entscheidung
    vorsteuer_ja = data.get("VORSTEUERBERECHTIGUNG") == "Ja"

    if vorsteuer_ja:
        data["REPARATURKOSTEN"] = rep_netto or rep_brutto
        data["GUTACHTERKOSTEN"] = gutachter_netto or gutachter_brutto
    else:
        data["REPARATURKOSTEN"] = rep_brutto or rep_netto
        data["GUTACHTERKOSTEN"] = gutachter_brutto or gutachter_netto

    # 13) Summenlogik Reparaturschaden
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

    data["KOSTENSUMME_X"] = data["KOSTENSUMME_REPARATUR"]

    # Reparaturschaden: diese Totalschaden-Felder bleiben leer
    data["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""
    data["KOSTENSUMME_TOTALSCHADEN"] = ""

    # 14) Plausibilitätsprüfung
    required = ["MANDANT_NAME", "AKTENZEICHEN", "KENNZEICHEN", "REPARATURKOSTEN", "WBW"]

    for key in required:
        if not data.get(key):
            warnings.append(f"{key} nicht gefunden")

    # Harte Schutzprüfung: Michael Hohlwein darf nicht Mandant werden
    if re.search(r"michael\s+hohlwein", data.get("MANDANT_NAME", ""), flags=re.I):
        data["_OK"] = False
        warnings.append("Mandant wurde fälschlich als Michael Hohlwein erkannt – Anspruchstellerblock prüfen")

    if warnings:
        data["_OK"] = False
        data["_WARNINGS"] = "; ".join(warnings)
    else:
        data["_OK"] = True
        data["_WARNINGS"] = ""

    return data
