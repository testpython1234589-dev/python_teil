from __future__ import annotations

import re
from typing import Dict, Any, List, Tuple

from common import (
    clean_text,
    cleanup_name,
    extract_money,
)

# =========================================================
# HELPERS
# =========================================================

STOP_WORDS = [
    "fahrzeug",
    "fabrikat",
    "typ",
    "versicherung",
    "schadennummer",
    "besichtigungsdatum",
    "kennzeichen",
    "reparaturkosten",
    "gutachten",
]


def _get_lines(text: str) -> List[str]:
    return [
        clean_text(line)
        for line in str(text).splitlines()
        if clean_text(line)
    ]


def _search_value(lines: List[str], patterns: List[str]) -> str:

    for line in lines:

        line_clean = clean_text(line)

        for pattern in patterns:

            m = re.search(pattern, line_clean, re.I)

            if m:
                return clean_text(m.group(1))

    return ""


def _extract_date(text: str, label: str) -> str:

    m = re.search(
        rf"{re.escape(label)}.*?(\d{{2}}\.\d{{2}}\.\d{{4}})",
        text,
        re.I,
    )

    if m:
        return m.group(1)

    return ""


def _extract_license_from_line(line: str) -> str:

    m = re.search(
        r"\b([A-ZÄÖÜ]{1,4}\-[A-Z]{1,3}\s?\d{1,4})\b",
        line,
        re.I,
    )

    if m:
        return clean_text(m.group(1))

    return ""


def _split_address(line: str) -> Tuple[str, str]:

    line = clean_text(line)

    if "," in line:

        left, right = line.split(",", 1)

        return clean_text(left), clean_text(right)

    m = re.search(r"(\d{5}\s+.+)", line)

    if m:

        plz_ort = clean_text(m.group(1))
        strasse = clean_text(line.replace(plz_ort, ""))

        return strasse, plz_ort

    return line, ""


def _looks_like_name(text: str) -> bool:

    t = text.lower()

    if any(x in t for x in STOP_WORDS):
        return False

    if re.search(r"\d{5}", text):
        return False

    if len(text.split()) > 5:
        return False

    return True


# =========================================================
# MANDANT
# =========================================================

def _extract_mandant_block(lines: List[str]):

    result = {
        "name": "",
        "strasse": "",
        "plz_ort": "",
    }

    for i, line in enumerate(lines):

        line_clean = clean_text(line)

        # -----------------------------------------
        # FALL:
        # Anspruchsteller Mandy Schramm
        # -----------------------------------------

        m = re.search(
            r"Anspruchsteller\s+(.+)",
            line_clean,
            re.I,
        )

        if not m:
            continue

        possible_name = clean_text(m.group(1))

        if not _looks_like_name(possible_name):
            continue

        result["name"] = possible_name

        # -----------------------------------------
        # nächste Zeile = adresse
        # -----------------------------------------

        if i + 1 < len(lines):

            adr = clean_text(lines[i + 1])

            strasse, plz_ort = _split_address(adr)

            result["strasse"] = strasse
            result["plz_ort"] = plz_ort

        break

    return (
        result["name"],
        result["strasse"],
        result["plz_ort"],
    )


# =========================================================
# VERSICHERUNG
# =========================================================

def _extract_versicherung(lines: List[str]):

    versicherung = ""
    ver_strasse = ""
    ver_ort = ""

    for i, line in enumerate(lines):

        line_clean = clean_text(line)

        # -----------------------------------------
        # Schadennummer - Versicherung AXA Versicherung
        # -----------------------------------------

        m = re.search(
            r"versicherung\s+(.+versicherung)",
            line_clean,
            re.I,
        )

        if not m:
            continue

        versicherung = clean_text(m.group(1))

        # -----------------------------------------
        # adresse meist 2 zeilen weiter
        # -----------------------------------------

        if i + 2 < len(lines):

            adr = clean_text(lines[i + 2])

            ver_strasse, ver_ort = _split_address(adr)

        break

    return versicherung, ver_strasse, ver_ort


# =========================================================
# ANREDE
# =========================================================

def _extract_anrede(lines: List[str]) -> str:

    for line in lines[:20]:

        txt = clean_text(line).lower()

        if txt == "herr":
            return "Herr"

        if txt == "frau":
            return "Frau"

    return ""


# =========================================================
# PARSER
# =========================================================

def parse_stotko(
    pages: List[str],
    pdf_source=None,
) -> Dict[str, Any]:

    first_page = pages[0] if pages else ""
    full = "\n".join(pages)

    lines = _get_lines(full)

    data: Dict[str, Any] = {}

    # =====================================================
    # AKTENZEICHEN
    # =====================================================

    data["AKTENZEICHEN"] = _search_value(
        lines,
        [
            r"Nr\.?\s*[:\-]?\s*(AP[0-9A-Z]+)",
            r"Gutachtennummer\s*[:\-]?\s*(.+)",
            r"Aktenzeichen\s*[:\-]?\s*(.+)",
        ],
    )

    # =====================================================
    # MANDANT
    # =====================================================

    raw_name, mandant_strasse, mandant_plz_ort = (
        _extract_mandant_block(lines)
    )

    _, clean_name = cleanup_name(raw_name)

    anrede = _extract_anrede(lines)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name
    data["MANDANT_STRASSE"] = mandant_strasse
    data["MANDANT_PLZ_ORT"] = mandant_plz_ort

    # -----------------------------------------------------

    if anrede.lower() == "herr":

        data["MANDANT_GENDER1"] = "Herr"
        data["MANDANT_GENDER2"] = ""

    elif anrede.lower() == "frau":

        data["MANDANT_GENDER1"] = ""
        data["MANDANT_GENDER2"] = "Frau"

    else:

        data["MANDANT_GENDER1"] = ""
        data["MANDANT_GENDER2"] = ""

    # =====================================================
    # KENNZEICHEN
    # =====================================================

    data["KENNZEICHEN_MANDANT"] = ""
    data["KENNZEICHEN_GEGNER"] = ""

    for line in lines:

        low = line.lower()

        if "kennzeichen" not in low:
            continue

        kennzeichen = _extract_license_from_line(line)

        if not kennzeichen:
            continue

        # AST = anspruchsteller
        if "(ast)" in low:

            data["KENNZEICHEN_MANDANT"] = kennzeichen

        # VN = versicherungsnehmer
        elif "(vn)" in low:

            data["KENNZEICHEN_GEGNER"] = kennzeichen

        # fallback
        elif not data["KENNZEICHEN_MANDANT"]:

            data["KENNZEICHEN_MANDANT"] = kennzeichen

    # =====================================================
    # VERSICHERUNG
    # =====================================================

    versicherung, ver_str, ver_ort = (
        _extract_versicherung(lines)
    )

    data["VERSICHERUNG"] = versicherung
    data["VER_STRASSE"] = ver_str
    data["VER_ORT"] = ver_ort

    # =====================================================
    # SCHADENSNUMMER
    # =====================================================

    data["SCHADENSNUMMER"] = _search_value(
        lines,
        [
            r"Schadennummer\s*[-:]?\s*(.+)",
            r"Schaden-Nr\.?\s*[:\-]?\s*(.+)",
        ],
    )

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

    fabrikat = _search_value(
        lines,
        [
            r"Fabrikat\s*[:\-]?\s*(.+)",
            r"Hersteller\s*[:\-]?\s*(.+)",
        ],
    )

    typ = _search_value(
        lines,
        [
            r"Typ\s*/\s*Untertyp\s*[:\-]?\s*(.+)",
            r"Untertyp\s*[:\-]?\s*(.+)",
        ],
    )

    typ = re.sub(
        r"\b(FR)\s+\1\b",
        r"\1",
        typ,
        flags=re.I,
    )

    data["FAHRZEUGTYP"] = clean_text(
        f"{fabrikat} {typ}".strip()
    )

    # =====================================================
    # WERTE
    # =====================================================

    data["WERTMINDERUNG"] = extract_money(
        full,
        [
            r"Wertminderung.*?([0-9\.\,]+)",
        ],
    )

    data["WBW"] = extract_money(
        full,
        [
            r"Wiederbeschaffungswert.*?([0-9\.\,]+)",
        ],
    )

    data["RESTWERT"] = extract_money(
        full,
        [
            r"Restwert.*?([0-9\.\,]+)",
        ],
    )

    # =====================================================
    # REPARATURKOSTEN
    # =====================================================

    data["REPARATURKOSTEN_NETTO"] = extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.?\s*([0-9\.\,]+)",
            r"Reparaturkosten netto\s*([0-9\.\,]+)",
        ],
    )

    data["REPARATURKOSTEN_BRUTTO"] = extract_money(
        full,
        [
            r"Reparaturkosten inkl\. MwSt\.?\s*([0-9\.\,]+)",
            r"Reparaturkosten brutto\s*([0-9\.\,]+)",
        ],
    )

    # =====================================================
    # GUTACHTERKOSTEN
    # =====================================================

    data["GUTACHTERKOSTEN_BRUTTO"] = extract_money(
        first_page,
        [
            r"Rechnungsbetrag brutto.*?([0-9\.\,]+)",
            r"Rechnungsbetrag inkl.*?([0-9\.\,]+)",
        ],
    )

    # =====================================================
    # FIX FELDER
    # =====================================================

    data.setdefault("WERTVERBESSERUNG", "")
    data.setdefault("UNFALL_UHRZEIT", "")
    data.setdefault("UNFALL_STRASSE", "")
    data.setdefault("UNFALL_ORT", "")

    # =====================================================
    # ZUSATZFELDER
    # =====================================================

    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    data["REPARATURKOSTEN"] = (
        data["REPARATURKOSTEN_NETTO"]
    )

    data["REPARATURSCHADEN"] = (
        data["REPARATURKOSTEN_NETTO"]
    )

    data["GUTACHTERKOSTEN"] = (
        data["GUTACHTERKOSTEN_BRUTTO"]
    )

    data["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""

    if data["WBW"] and data["RESTWERT"]:

        try:

            wbw = float(
                data["WBW"]
                .replace(".", "")
                .replace(",", ".")
                .replace("€", "")
                .strip()
            )

            restwert = float(
                data["RESTWERT"]
                .replace(".", "")
                .replace(",", ".")
                .replace("€", "")
                .strip()
            )

            diff = wbw - restwert

            data["WIEDERBESCHAFFUNGSWERTAUFWAND"] = (
                f"{diff:,.2f} €"
                .replace(",", "X")
                .replace(".", ",")
                .replace("X", ".")
            )

        except:
            pass

    # =====================================================
    # PARSER INFO
    # =====================================================

    data["_PARSER"] = "stotko"

    return data
