from __future__ import annotations

import re
from typing import Dict, Any, List

from common import (
    clean_text,
    cleanup_name,
    extract_money,
)

# =========================================================
# HELPERS
# =========================================================

def _normalize_text(text: str) -> str:

    text = str(text)

    text = text.replace("|", " ")
    text = text.replace("ﬁ", "fi")
    text = text.replace("ﬂ", "fl")

    text = re.sub(r"[ \t]+", " ", text)

    return text


def _to_float(value):

    if not value:
        return 0.0

    value = (
        str(value)
        .replace("€", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )

    try:
        return float(value)
    except:
        return 0.0


def _to_euro(value):

    return (
        f"{value:,.2f} €"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def _get_lines(text: str) -> List[str]:

    return [
        clean_text(x)
        for x in str(text).splitlines()
        if clean_text(x)
    ]


def _money(
    text: str,
    patterns: List[str],
) -> str:

    return extract_money(text, patterns)


def _extract_date(
    text: str,
    label: str,
) -> str:

    m = re.search(
        rf"{re.escape(label)}.*?(\d{{2}}\.\d{{2}}\.\d{{4}})",
        text,
        re.I,
    )

    if m:
        return m.group(1)

    return ""


def _extract_license(text: str) -> str:

    m = re.search(
        r"\b([A-ZÄÖÜ]{1,4}\-[A-Z]{1,3}\s?\d{1,4})\b",
        text,
        re.I,
    )

    if m:
        return clean_text(m.group(1))

    return ""


def _split_address(line: str):

    line = clean_text(line)

    if "," in line:

        left, right = line.split(",", 1)

        return (
            clean_text(left),
            clean_text(right),
        )

    m = re.search(
        r"(.+?)\s+(\d{5}\s+.+)",
        line,
    )

    if m:

        return (
            clean_text(m.group(1)),
            clean_text(m.group(2)),
        )

    return line, ""


# =========================================================
# MANDANT
# =========================================================

def _extract_mandant(lines):

    result = {
        "anrede": "",
        "name": "",
        "strasse": "",
        "plz_ort": "",
    }

    for i, line in enumerate(lines[:50]):

        low = line.lower()

        if low not in ["herr", "frau"]:
            continue

        result["anrede"] = line

        # -----------------------------------
        # NAME
        # -----------------------------------

        if i + 1 < len(lines):

            possible_name = clean_text(lines[i + 1])

            if (
                not re.search(r"\d", possible_name)
                and len(possible_name.split()) <= 5
            ):
                result["name"] = possible_name

        # -----------------------------------
        # STRASSE
        # -----------------------------------

        if i + 2 < len(lines):

            possible_street = clean_text(lines[i + 2])

            # Straße + PLZ in gleicher Zeile
            m = re.search(
                r"(.+?\d+[a-zA-Z]?)\s+(\d{5}\s+.+)",
                possible_street,
            )

            if m:

                result["strasse"] = clean_text(
                    m.group(1)
                )

                result["plz_ort"] = clean_text(
                    m.group(2)
                )

            elif re.search(r"\d", possible_street):

                result["strasse"] = possible_street

        # -----------------------------------
        # PLZ ORT
        # -----------------------------------

        if (
            not result["plz_ort"]
            and i + 3 < len(lines)
        ):

            possible_city = clean_text(lines[i + 3])

            if re.search(r"\b\d{5}\b", possible_city):

                result["plz_ort"] = possible_city

        break

    return result


# =========================================================
# VERSICHERUNG
# =========================================================

def _extract_versicherung(lines):

    result = {
        "versicherung": "",
        "strasse": "",
        "ort": "",
    }

    for i, line in enumerate(lines):

        low = line.lower()

        if "versicherung" not in low:
            continue

        if "versicherungsschein" in low:
            continue

        # -----------------------------------
        # Versicherung
        # -----------------------------------

        m = re.search(
            r"\b((?:[A-ZÄÖÜ0-9]+[\s\-]*){1,4}Versicherung)\b",
            line,
            re.I,
        )

        if m:

            value = clean_text(m.group(1))

            value = re.sub(
                r"^Versicherung\s+",
                "",
                value,
                flags=re.I,
            )

            result["versicherung"] = value

        # -----------------------------------
        # Adresse
        # -----------------------------------

        for j in range(i, min(i + 5, len(lines))):

            current = clean_text(lines[j])

            if "," in current and re.search(r"\d{5}", current):

                street, city = _split_address(current)

                result["strasse"] = street
                result["ort"] = city

                break

        if result["versicherung"]:
            break

    return result


# =========================================================
# KENNZEICHEN
# =========================================================

def _extract_kennzeichen(lines):

    result = {
        "mandant": "",
        "gegner": "",
    }

    for line in lines:

        low = line.lower()

        if "kennzeichen" not in low:
            continue

        kz = _extract_license(line)

        if not kz:
            continue

        if "(ast)" in low:

            result["mandant"] = kz

        elif "(vn)" in low:

            result["gegner"] = kz

    return result


# =========================================================
# AKTENZEICHEN
# =========================================================

def _extract_aktenzeichen(lines):

    for line in lines[:40]:

        m = re.search(
            r"\b(AP[0-9A-Z]+)\b",
            line,
            re.I,
        )

        if m:
            return clean_text(m.group(1))

    return ""


# =========================================================
# FAHRZEUG
# =========================================================

def _extract_fahrzeugtyp(lines):

    fabrikat = ""
    typ = ""

    for line in lines:

        m1 = re.search(
            r"Fabrikat:\s*(.+)",
            line,
            re.I,
        )

        if m1:
            fabrikat = clean_text(m1.group(1))

        m2 = re.search(
            r"Typ\s*/\s*Untertyp:\s*(.+)",
            line,
            re.I,
        )

        if m2:
            typ = clean_text(m2.group(1))

    typ = re.sub(
        r"\b(FR)\s+\1\b",
        r"\1",
        typ,
        flags=re.I,
    )

    return clean_text(
        f"{fabrikat} {typ}".strip()
    )


# =========================================================
# PARSER
# =========================================================

def parse_stotko(
    pages: List[str],
    pdf_source=None,
) -> Dict[str, Any]:

    full = "\n".join(pages)
    full = _normalize_text(full)

    first_page = pages[0] if pages else ""
    first_page = _normalize_text(first_page)

    lines = _get_lines(full)

    data: Dict[str, Any] = {}

    # =====================================================
    # AKTENZEICHEN
    # =====================================================

    data["AKTENZEICHEN"] = _extract_aktenzeichen(
        lines
    )

    # =====================================================
    # MANDANT
    # =====================================================

    mandant = _extract_mandant(lines)

    raw_name = mandant["name"]

    title, clean_name = cleanup_name(raw_name)

    data["MANDANT_ANREDE"] = mandant["anrede"]

    data["MANDANT_NAME"] = clean_name
    data["MANDANT_TITEL"] = title

    data["MANDANT_STRASSE"] = mandant["strasse"]
    data["MANDANT_PLZ_ORT"] = mandant["plz_ort"]

    data["MANDANT_VOLLNAME"] = clean_name

    split_name = clean_name.split()

    if len(split_name) >= 2:

        data["MANDANT_VORNAME"] = split_name[0]

        data["MANDANT_NACHNAME"] = " ".join(
            split_name[1:]
        )

    else:

        data["MANDANT_VORNAME"] = ""
        data["MANDANT_NACHNAME"] = ""

    # =====================================================
    # GENDER
    # =====================================================

    if mandant["anrede"].lower() == "frau":

        data["MANDANT_GENDER1"] = ""
        data["MANDANT_GENDER2"] = "Frau"

        data["GENDER1"] = "Ihrer"
        data["GENDER2"] = "meiner Mandantin"

    elif mandant["anrede"].lower() == "herr":

        data["MANDANT_GENDER1"] = "Herr"
        data["MANDANT_GENDER2"] = ""

        data["GENDER1"] = "Ihrem"
        data["GENDER2"] = "meinem Mandanten"

    else:

        data["MANDANT_GENDER1"] = ""
        data["MANDANT_GENDER2"] = ""

        data["GENDER1"] = ""
        data["GENDER2"] = ""

    data["GENDERN"] = data["GENDER1"]
    data["GENDERN1"] = data["GENDER1"]
    data["GENDERN2"] = data["GENDER2"]

    # =====================================================
    # VERSICHERUNG
    # =====================================================

    ver = _extract_versicherung(lines)

    data["VERSICHERUNG"] = ver["versicherung"]
    data["VRSICHERUNG"] = ver["versicherung"]

    data["VER_STRASSE"] = ver["strasse"]
    data["VER_ORT"] = ver["ort"]

    # =====================================================
    # KENNZEICHEN
    # =====================================================

    kz = _extract_kennzeichen(lines)

    data["KENNZEICHEN_MANDANT"] = kz["mandant"]
    data["KENNZEICHEN_GEGNER"] = kz["gegner"]

    data["KENNZEICHEN"] = kz["mandant"]
    data["EIGENES_KENNZEICHEN"] = kz["mandant"]

    # =====================================================
    # SCHADENSNUMMER
    # =====================================================

    m = re.search(
        r"Schadennummer.*?([0-9\/\-\s]+)",
        full,
        re.I,
    )

    if not m:

        m = re.search(
            r"Versicherungsnummer.*?([0-9\/\-\s]+)",
            full,
            re.I,
        )

    if m:

        data["SCHADENSNUMMER"] = clean_text(
            m.group(1)
        )

    else:

        data["SCHADENSNUMMER"] = ""

    # =====================================================
    # DATEN
    # =====================================================

    data["BESICHTIGUNGSDATUM"] = _extract_date(
        full,
        "Besichtigungsdatum",
    )

    data["UNFALL_DATUM"] = (
        _extract_date(full, "Ereignis vom")
        or _extract_date(full, "Unfalltag")
    )

    # =====================================================
    # FAHRZEUG
    # =====================================================

    data["FAHRZEUGTYP"] = _extract_fahrzeugtyp(
        lines
    )

    # =====================================================
    # GELDWERTE
    # =====================================================

    data["WERTMINDERUNG"] = _money(
        full,
        [
            r"Wertminderung.*?([0-9\.\,]+)",
        ],
    )

    data["WBW"] = _money(
        full,
        [
            r"Wiederbeschaffungswert.*?([0-9\.\,]+)",
        ],
    )

    data["RESTWERT"] = _money(
        full,
        [
            r"Restwert.*?([0-9\.\,]+)",
        ],
    )

    # =====================================================
    # REPARATURKOSTEN
    # =====================================================

    data["REPARATURKOSTEN_NETTO"] = _money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.?\s*([0-9\.\,]+)",
            r"Reparaturkosten netto\s*([0-9\.\,]+)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = _money(
        full,
        [
            r"Reparaturkosten brutto\s*([0-9\.\,]+)",
            r"Reparaturkosten inkl\. MwSt\.?\s*([0-9\.\,]+)",
        ],
    )

    data["REPARATURKOSTEN"] = (
        data["REPARATURKOSTEN_NETTO"]
    )

    data["REPARATURSCHADEN"] = (
        data["REPARATURKOSTEN_NETTO"]
    )

    # =====================================================
    # GUTACHTERKOSTEN
    # =====================================================

    data["GUTACHTERKOSTEN_BRUTTO"] = _money(
        first_page,
        [
            r"Rechnungsbetrag brutto.*?([0-9\.\,]+)",
            r"Rechnungsbetrag inkl.*?([0-9\.\,]+)",
        ],
    )

    data["GUTACHTERKOSTEN"] = (
        data["GUTACHTERKOSTEN_BRUTTO"]
    )

    # =====================================================
    # SUMMEN
    # =====================================================

    rep = _to_float(
        data["REPARATURKOSTEN_BRUTTO"]
    )

    gut = _to_float(
        data["GUTACHTERKOSTEN_BRUTTO"]
    )

    wm = _to_float(
        data["WERTMINDERUNG"]
    )

    data["KOSTENSUMME_REPARATUR"] = _to_euro(
        rep + gut + wm + 25
    )

    wbw = _to_float(data["WBW"])

    data["KOSTENSUMME_TOTALSCHADEN"] = _to_euro(
        wbw + gut + 25
    )

    data["KOSTENSUMME_X"] = (
        data["KOSTENSUMME_REPARATUR"]
    )

    # =====================================================
    # FIX FELDER
    # =====================================================

    data.setdefault("UNFALL_UHRZEIT", "")
    data.setdefault("UNFALL_STRASSE", "")
    data.setdefault("UNFALL_ORT", "")

    data.setdefault("WERTVERBESSERUNG", "")

    data.setdefault("WERTVERBESSERUNG_NAME", "")
    data.setdefault("WERTBESSERUNG_BETRAG", "")

    data["WERTMINDERUNG_NAME"] = "Wertminderung"

    data["WERTMINDERUNG_BETRAG"] = (
        data["WERTMINDERUNG"]
    )

    data.setdefault(
        "KOSTENPAUSCHALE",
        "25,00 €",
    )

    # =====================================================
    # ZUSATZFELDER
    # =====================================================

    data.setdefault("VORSTEUERABZUG_RAW", "")
    data.setdefault("VORSTEUERBERECHTIGUNG", "")

    data.setdefault(
        "ZUSATZKOSTEN_BEZEICHNUNG1",
        "",
    )

    data.setdefault(
        "ZUSATZKOSTEN_BETRAG1",
        "",
    )

    data.setdefault(
        "ZUSATZKOSTEN_BEZEICHNUNG2",
        "",
    )

    data.setdefault(
        "ZUSATZKOSTEN_BETRAG2",
        "",
    )

    data.setdefault(
        "ZUSATZKOSTEN_BEZEICHNUNG3",
        "",
    )

    data.setdefault(
        "ZUSATZKOSTEN_BETRAG3",
        "",
    )

    data.setdefault("MELDUNGSKOSTEN", "")

    # =====================================================
    # WBW AUFWAND
    # =====================================================

    wbw = _to_float(data["WBW"])
    restwert = _to_float(data["RESTWERT"])

    if wbw > 0:

        data["WIEDERBESCHAFFUNGSWERTAUFWAND"] = (
            _to_euro(wbw - restwert)
        )

    else:

        data["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""

    # =====================================================
    # PARSER
    # =====================================================

    data["_PARSER"] = "stotko"

    return data
