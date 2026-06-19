from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timedelta
import re

import gutachten_extractor as gx


# ============================================================
# nfz_standard_extractor.py
# NFZ Standard Parser – Reparaturschaden
# ============================================================


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
    for page in pages:
        low = (page or "").lower()
        if all(k.lower() in low for k in keywords):
            return page
    return ""


def _cut_before(text: str, patterns: List[str]) -> str:
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
    lines = _lines(block)
    label_low = label.lower()

    for i, line in enumerate(lines):
        low = line.lower()

        if low.startswith(label_low + " "):
            return _one_line(line[len(label):])

        if low == label_low and i + 1 < len(lines):
            return _one_line(lines[i + 1])

    return ""


def _parse_eur(value: str) -> Optional[Decimal]:
    if not value:
        return None

    s = str(value)
    s = s.replace("€", "").replace("\xa0", " ").strip()
    s = re.sub(r"[^0-9,.\-]", "", s)

    if not s:
        return None

    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
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
    s = f"{value:,.2f}"
    s = s.replace(",", "X")
    s = s.replace(".", ",")
    s = s.replace("X", ".")
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


def _add_days(date_str: str, days: int) -> str:
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return (dt + timedelta(days=days)).strftime("%d.%m.%Y")
    except Exception:
        return ""


def _extract_unfall_ort_nfz_standard(beteiligte_page: str) -> str:
    lines = _lines(beteiligte_page)

    in_unfall_block = False

    for i, line in enumerate(lines):
        low = line.lower().strip()

        if low.startswith("unfall datum"):
            in_unfall_block = True
            continue

        if in_unfall_block and (low == "ort" or low.startswith("ort ")):
            if low == "ort":
                parts = []
            else:
                parts = [line[len("Ort "):].strip()]

            j = i + 1

            while j < len(lines):
                nxt = lines[j].strip()
                nxt_low = nxt.lower().strip()

                if (
                    nxt_low.startswith("datum ")
                    or nxt_low.startswith("besichtigung")
                    or nxt_low.startswith("sachverständiger")
                    or nxt_low.startswith("unfallgegner")
                    or nxt_low.startswith("auftrag")
                ):
                    break

                parts.append(nxt)
                j += 1

            return _one_line(", ".join(p.strip(" ,") for p in parts if p.strip()))

    return ""


def _extract_unfallgegner_nfz_standard(beteiligte_page: str) -> Dict[str, str]:
    result = {
        "UNFALLGEGNER_NAME": "",
        "UNFALLGEGNER_STRASSE": "",
        "UNFALLGEGNER_PLZ_ORT": "",
    }

    if not beteiligte_page:
        return result

    lines = _lines(beteiligte_page)

    block_lines: List[str] = []
    in_block = False

    for line in lines:
        low = line.lower().strip()

        if low.startswith("unfallgegner"):
            in_block = True

            rest = re.sub(r"^unfallgegner\s*", "", line, flags=re.I).strip()

            if rest:
                block_lines.append(rest)

            continue

        if in_block:
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

            name = cleaned
            break

    result["UNFALLGEGNER_NAME"] = name
    result["UNFALLGEGNER_STRASSE"] = strasse
    result["UNFALLGEGNER_PLZ_ORT"] = plz_ort

    return result


def _extract_claimant_from_beteiligte_page(beteiligte_page: str) -> Dict[str, str]:
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
        "ANSPRECHPARTNER_ANREDE": "",
        "ANSPRECHPARTNER_NAME": "",
        "ANSPRECHPARTNER_VORNAME": "",
        "ANSPRECHPARTNER_NACHNAME": "",
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

    claimant_block = _cut_before(
        beteiligte_page,
        [
            r"\n\s*Kanzlei\b",
            r"\n\s*Anwalt\b",
            r"\bKanzlei\s+Rechtsanwalt\b",
            r"\n\s*Unfall\s+Datum\b",
        ],
    )

    claimant_block = re.sub(
        r"^.*?Beteiligte,\s*Besichtigungen\s*&\s*Auftrag",
        "",
        claimant_block,
        flags=re.S | re.I,
    )

    firma = _value_after_label(claimant_block, "Name")

    if not firma:
        firma = _search_first(
            claimant_block,
            [
                r"Name\s+(.+?)(?:\n|Herrn?\s|Frau\s|Straße\s|PLZ\s*Ort\s|Vorsteuerabzug\s)",
            ],
        )

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
    firma = _one_line(firma)

    result["ANSPRECHPARTNER_ANREDE"] = anrede
    result["ANSPRECHPARTNER_NAME"] = person
    result["ANSPRECHPARTNER_VORNAME"] = vorname
    result["ANSPRECHPARTNER_NACHNAME"] = nachname

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
        "ANSPRECHPARTNER_ANREDE": "",
        "ANSPRECHPARTNER_NAME": "",
        "ANSPRECHPARTNER_VORNAME": "",
        "ANSPRECHPARTNER_NACHNAME": "",
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

    result["ANSPRECHPARTNER_ANREDE"] = anrede
    result["ANSPRECHPARTNER_NAME"] = person
    result["ANSPRECHPARTNER_VORNAME"] = vorname
    result["ANSPRECHPARTNER_NACHNAME"] = nachname

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


def parse_nfz_standard(pages, pdf_source=None) -> Dict[str, Any]:
    pages = list(pages or [])
    full = "\n".join(pages)

    invoice_page = _get_page(pages, "Rechnung Nr.", "Gesamtbetrag ohne MwSt")
    summary_page = _get_page(pages, "Zusammenfassung", "Reparaturkosten")
    beteiligte_page = _get_page(pages, "Beteiligte", "Vorsteuerabzug")
    vehicle_page = _get_page(pages, "Fahrzeugdaten", "Amtliches Kennzeichen")

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

        "ANSPRECHPARTNER_ANREDE": "",
        "ANSPRECHPARTNER_NAME": "",
        "ANSPRECHPARTNER_VORNAME": "",
        "ANSPRECHPARTNER_NACHNAME": "",

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

        "VERSICHERUNG": "",
        "VRSICHERUNG": "",
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

    claimant = _extract_claimant_from_beteiligte_page(beteiligte_page)

    if not claimant.get("MANDANT_NAME"):
        claimant = _extract_claimant_from_invoice(invoice_page)

    data.update(claimant)

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

    data["UNFALL_ORT"] = (
        _extract_unfall_ort_nfz_standard(beteiligte_page)
        or _one_line(
            _search_first(
                beteiligte_page or full,
                [
                    r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\nUhrzeit\s+[^\n]+\nOrt\s+(.+?)(?:\nDatum|\nBesichtigung)",
                    r"Uhrzeit\s+[^\n]+\nOrt\s+(.+?)(?:\nDatum|\nBesichtigung)",
                    r"Ort\s+(Poco\s+Einrichtungsmärkte.+?)(?:\nDatum|\nBesichtigung)",
                ],
            )
        )
    )

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
    data["KENNZEICHEN_GEGNER"] = ""

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

    if data["HERSTELLER"] and data["MODELL"]:
        data["FAHRZEUGTYP"] = f'{data["HERSTELLER"]} {data["MODELL"]}'
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

    unfallgegner = _extract_unfallgegner_nfz_standard(beteiligte_page)

    data["UNFALLGEGNER_NAME"] = unfallgegner.get("UNFALLGEGNER_NAME", "")
    data["UNFALLGEGNER_STRASSE"] = unfallgegner.get("UNFALLGEGNER_STRASSE", "")
    data["UNFALLGEGNER_PLZ_ORT"] = unfallgegner.get("UNFALLGEGNER_PLZ_ORT", "")
    data["ANSPRUCHSGEGNER"] = data["UNFALLGEGNER_NAME"]

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

    if versicherung_name:
        data["VERSICHERUNG"] = _one_line(versicherung_name)
        data["VRSICHERUNG"] = _one_line(versicherung_name)
        data["VER_STRASSE"] = _one_line(versicherung_strasse)
        data["VER_ORT"] = _one_line(versicherung_ort)
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

    if (
        re.search(r"Es\s+handelt\s+sich\s+um\s+einen\s+Reparaturschaden", full, flags=re.I)
        or re.search(r"Schadenklasse\s*:\s*Reparaturschaden", full, flags=re.I)
    ):
        data["SCHADENART"] = "Reparaturschaden"
        data["REPARATURSCHADEN"] = "Ja"

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

    gutachter_netto = _extract_money(
        invoice_page or full,
        [
            r"Gesamtbetrag\s+ohne\s+MwSt\
