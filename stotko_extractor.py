from __future__ import annotations

import re
from typing import Dict, Any, List

from common import (
    clean_text,
    cleanup_name,
    extract_money,
)

# -------------------------
# HELPERS
# -------------------------

def _get_lines(text: str) -> List[str]:
    return [clean_text(line) for line in str(text).splitlines() if clean_text(line)]


def _value_after_inline_label(lines: List[str], label: str) -> str:
    label_norm = clean_text(label).lower()

    for line in lines:
        line_clean = clean_text(line)
        if line_clean.lower().startswith(label_norm):
            return clean_text(line_clean[len(label):].strip(" :"))
    return ""


def _extract_header_anrede(lines: List[str]) -> str:
    for line in lines[:15]:
        txt = clean_text(line).lower()
        if txt == "herr":
            return "Herr"
        if txt == "frau":
            return "Frau"
    return ""


def _split_street_plz_ort(line: str):
    line = clean_text(line)

    # PLZ erkennen
    m = re.search(r"\b\d{5}\b.*", line)
    if m:
        plz_ort = m.group(0)
        strasse = line.replace(plz_ort, "").strip(", ")
        return strasse, plz_ort

    return line, ""


def _extract_mandant_block(lines: List[str]):
    """
    Robuste Erkennung für Stotko:
    Funktioniert für:
    - Anspruchsteller: Max Mustermann
    - Anspruchsteller:
      Max Mustermann
      Straße
      PLZ Ort
    - Mit oder ohne Anrede
    """

    name = ""
    strasse = ""
    plz_ort = ""

    for i, line in enumerate(lines):
        l = clean_text(line).lower()

        if "anspruchsteller" in l:

            # ---- NAME ----
            raw_name = _value_after_inline_label([line], "Anspruchsteller")

            if raw_name:
                name = raw_name
                offset = 1
            else:
                # Name steht in nächster Zeile
                if i + 1 < len(lines):
                    name = lines[i + 1]
                offset = 2

            # ---- ADRESSE (mehrere Varianten testen) ----
            candidates = []

            for j in range(i + offset, min(i + offset + 4, len(lines))):
                candidates.append(lines[j])

            # Suche PLZ zuerst (stabilster Marker)
            for c in candidates:
                if re.search(r"\b\d{5}\b", c):
                    plz_ort = c
                    break

            # Straße = Zeile davor
            if plz_ort:
                idx = candidates.index(plz_ort)
                if idx > 0:
                    strasse = candidates[idx - 1]
            else:
                # Fallback (alte Logik)
                if len(candidates) >= 2:
                    strasse = candidates[0]
                    plz_ort = candidates[1]

            break

    return name, strasse, plz_ort


# -------------------------
# PARSER
# -------------------------

def parse_stotko(pages: List[str], pdf_source=None) -> Dict[str, Any]:
    first_page = pages[0] if pages else ""
    full = "\n".join(pages)

    data: Dict[str, Any] = {}

    all_lines = _get_lines(full)

    # -------------------------
    # AKTENZEICHEN
    # -------------------------
    data["AKTENZEICHEN"] = (
        _value_after_inline_label(all_lines, "Gutachtennummer")
        or _value_after_inline_label(all_lines, "Aktenzeichen")
    )

    # -------------------------
    # MANDANT (FIX)
    # -------------------------
    raw_name, mandant_strasse, mandant_plz_ort = _extract_mandant_block(all_lines)

    _, clean_name = cleanup_name(raw_name)

    anrede = _extract_header_anrede(all_lines)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name
    data["MANDANT_STRASSE"] = mandant_strasse
    data["MANDANT_PLZ_ORT"] = mandant_plz_ort

    # OPTIONAL: Gender wie bei schnur
    if anrede.lower() == "herr":
        data["MANDANT_GENDER1"] = "Herr"
        data["MANDANT_GENDER2"] = ""
    elif anrede.lower() == "frau":
        data["MANDANT_GENDER1"] = ""
        data["MANDANT_GENDER2"] = "Frau"
    else:
        data["MANDANT_GENDER1"] = ""
        data["MANDANT_GENDER2"] = ""

    # -------------------------
    # KENNZEICHEN
    # -------------------------
    data["KENNZEICHEN_MANDANT"] = _value_after_inline_label(all_lines, "Amtliches Kennzeichen")

    data["KENNZEICHEN_GEGNER"] = (
        _value_after_inline_label(all_lines, "Kennzeichen Unfallgegner")
        or _value_after_inline_label(all_lines, "Kennzeichen Gegner")
    )

    # -------------------------
    # VERSICHERUNG
    # -------------------------
    data["VERSICHERUNG"] = _value_after_inline_label(all_lines, "Versicherung")

    for i, line in enumerate(all_lines):
        if "versicherung" in line.lower():
            if i + 2 < len(all_lines):
                data["VER_STRASSE"] = all_lines[i + 1]
                data["VER_ORT"] = all_lines[i + 2]
            break

    # -------------------------
    # SCHADENSNUMMER
    # -------------------------
    data["SCHADENSNUMMER"] = (
        _value_after_inline_label(all_lines, "Schadennummer")
        or _value_after_inline_label(all_lines, "Schaden-Nr.")
    )

    # -------------------------
    # DATEN
    # -------------------------
    data["BESICHTIGUNGSDATUM"] = _value_after_inline_label(all_lines, "Besichtigungsdatum")

    data["UNFALL_DATUM"] = (
        _value_after_inline_label(all_lines, "Ereignis vom")
        or _value_after_inline_label(all_lines, "Unfalltag")
    )

    # -------------------------
    # FAHRZEUG
    # -------------------------
    typ = _value_after_inline_label(all_lines, "Typ / Untertyp")
    fabrikat = _value_after_inline_label(all_lines, "Fabrikat")

    data["FAHRZEUGTYP"] = clean_text(f"{fabrikat} {typ}".strip())

    # -------------------------
    # WERTE
    # -------------------------
    data["WERTMINDERUNG"] = extract_money(full, [r"Wertminderung.*?([0-9\.\,]+)"])
    data["WBW"] = extract_money(full, [r"Wiederbeschaffungswert.*?([0-9\.\,]+)"])
    data["RESTWERT"] = extract_money(full, [r"Restwert.*?([0-9\.\,]+)"])

    # -------------------------
    # REPARATUR
    # -------------------------
    data["REPARATURKOSTEN_NETTO"] = extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.\s*EUR\s*([0-9\.\,]+)",
            r"Reparaturkosten netto\s*([0-9\.\,]+)",
        ],
    )

    # -------------------------
    # GUTACHTERKOSTEN
    # -------------------------
    data["GUTACHTERKOSTEN_BRUTTO"] = extract_money(
        first_page,
        [
            r"Rechnungsbetrag brutto\s*EUR\s*([0-9\.\,]+)",
            r"Rechnungsbetrag inkl\.\s*MwSt.*?EUR\s*([0-9\.\,]+)",
        ],
    )

    # -------------------------
    # FIX FELDER
    # -------------------------
    data.setdefault("WERTVERBESSERUNG", "")
    data.setdefault("UNFALL_UHRZEIT", "")
    data.setdefault("UNFALL_STRASSE", "")
    data.setdefault("UNFALL_ORT", "")

    data["_PARSER"] = "stotko"

    return data
