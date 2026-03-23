from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Iterable

from pypdf import PdfReader


SECTION_HEADINGS = [
    "Anspruchsteller",
    "Anwalt",
    "Unfall",
    "Besichtigung",
    "Unfallgegner",
    "Versicherung",
    "Auftrag",
    "Zusammenfassung",
    "Schadenhöhe",
    "Reparatur",
    "Nutzungsausfall",
    "Fahrzeugwert",
]

SURNAME_JOINERS = {
    "von", "van", "de", "del", "der", "den", "zu", "zur", "zum",
    "al", "el", "bin", "ibn", "abu", "abi"
}


def pdf_to_text(pdf_source: str | Path | bytes) -> str:
    if isinstance(pdf_source, (str, Path)):
        reader = PdfReader(str(pdf_source))
    else:
        reader = PdfReader(BytesIO(pdf_source))

    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")

    text = "\n".join(pages)
    text = text.replace("\xa0", " ")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def normalize_lines(text: str) -> List[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return lines


def split_sections(lines: List[str]) -> Dict[str, List[str]]:
    positions = []
    heading_map = {h.casefold(): h for h in SECTION_HEADINGS}

    for idx, line in enumerate(lines):
        key = line.casefold()
        if key in heading_map:
            positions.append((idx, heading_map[key]))

    sections: Dict[str, List[str]] = {}
    for i, (start_idx, heading) in enumerate(positions):
        end_idx = positions[i + 1][0] if i + 1 < len(positions) else len(lines)
        sections[heading] = lines[start_idx + 1:end_idx]

    return sections


def line_matches_label(line: str, label: str) -> bool:
    return line == label or line.startswith(label + " ")


def detect_label(line: str, labels: Iterable[str]) -> str | None:
    for label in labels:
        if line_matches_label(line, label):
            return label
    return None


def parse_labeled_section(lines: List[str], labels: List[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    i = 0

    while i < len(lines):
        current = lines[i]
        label = detect_label(current, labels)

        if not label:
            i += 1
            continue

        value_parts: List[str] = []

        # Fall: "Label Wert" in einer Zeile
        if current != label:
            inline_val = current[len(label):].strip(" :-")
            if inline_val:
                value_parts.append(inline_val)

        i += 1

        # Folgezeilen bis zum nächsten Label
        while i < len(lines):
            nxt = lines[i]
            if detect_label(nxt, labels):
                break
            value_parts.append(nxt.strip())
            i += 1

        result[label] = " ".join(x for x in value_parts if x).strip()

    return result


def first_line_after(lines: List[str], label: str) -> str:
    for i, line in enumerate(lines):
        if line == label:
            if i + 1 < len(lines):
                return lines[i + 1].strip()
        if line.startswith(label + " "):
            return line[len(label):].strip(" :-")
    return ""


def first_regex(text: str, patterns: Iterable[str], flags=re.IGNORECASE | re.MULTILINE | re.DOTALL) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return m.group(1).strip()
    return ""


def extract_money_token(value: str) -> str:
    if not value:
        return ""
    m = re.search(r"[+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2}", value)
    if m:
        return m.group(0).replace(" ", "")
    m = re.search(r"[+-]?\s*\d+(?:,\d{2})", value)
    if m:
        return m.group(0).replace(" ", "")
    return ""


def normalize_money_str(value: str) -> str:
    token = extract_money_token(value)
    if not token:
        return ""
    token = token.replace(".", "").replace(",", ".")
    try:
        dec = Decimal(token)
        s = f"{dec:,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except (InvalidOperation, ValueError):
        return ""


def money_to_decimal(value: str) -> Decimal | None:
    token = extract_money_token(value)
    if not token:
        return None
    token = token.replace(".", "").replace(",", ".")
    try:
        return Decimal(token)
    except (InvalidOperation, ValueError):
        return None


def format_decimal_de(value: Decimal) -> str:
    s = f"{value:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def is_yes(value: str) -> bool:
    return str(value).strip().lower() in {"ja", "yes", "y", "true", "1"}


def is_no(value: str) -> bool:
    return str(value).strip().lower() in {"nein", "no", "n", "false", "0"}


def normalize_yes_no(value: str) -> str:
    if is_yes(value):
        return "Ja"
    if is_no(value):
        return "Nein"
    return str(value).strip()


def cleanup_person_name(raw: str) -> tuple[str, str]:
    """
    Gibt (Anrede, NameOhneAnrede) zurück.
    'Herr Dr. Motaz Abi Zamr' -> ('Herr', 'Dr. Motaz Abi Zamr')
    """
    raw = re.sub(r"\s+", " ", (raw or "")).strip()
    if re.match(r"(?i)^herr\b", raw):
        return "Herr", re.sub(r"(?i)^herr\b\.?\s*", "", raw).strip()
    if re.match(r"(?i)^frau\b", raw):
        return "Frau", re.sub(r"(?i)^frau\b\.?\s*", "", raw).strip()
    return "", raw


def split_first_last_name(full_name: str) -> tuple[str, str]:
    name = re.sub(r"\s+", " ", (full_name or "")).strip()
    if not name:
        return "", ""

    parts = name.split()
    if len(parts) == 1:
        return "", parts[0]

    # "Abi Zamr", "von Müller", "al X" etc. als Nachname zusammenhalten
    if len(parts) >= 3 and parts[-2].lower().strip(".") in SURNAME_JOINERS:
        last = f"{parts[-2]} {parts[-1]}"
        first = " ".join(parts[:-2])
        return first.strip(), last.strip()

    return " ".join(parts[:-1]).strip(), parts[-1].strip()


def split_street_and_place(value: str) -> tuple[str, str]:
    value = re.sub(r"\s+", " ", (value or "")).strip()
    if not value:
        return "", ""

    if "," in value:
        street, rest = value.split(",", 1)
        return street.strip(), rest.strip(" -")
    return "", value


def money_from_labeled_lines(lines: List[str], labels: List[str]) -> str:
    for label in labels:
        val = first_line_after(lines, label)
        norm = normalize_money_str(val)
        if norm:
            return norm

    joined = "\n".join(lines)
    for label in labels:
        pat = rf"{re.escape(label)}(?:\s*\([^\)]*\))?\s*([+-]?\s*\d{{1,3}}(?:\.\d{{3}})*,\d{{2}})"
        m = re.search(pat, joined, re.IGNORECASE)
        if m:
            norm = normalize_money_str(m.group(1))
            if norm:
                return norm
    return ""


def extract_all(text: str) -> Dict[str, Any]:
    lines = normalize_lines(text)
    sections = split_sections(lines)
    full_text = "\n".join(lines)

    data: Dict[str, Any] = {}

    # -------------------------
    # 1) Anspruchsteller
    # -------------------------
    anspruchsteller = parse_labeled_section(
        sections.get("Anspruchsteller", []),
        ["Name", "Straße", "PLZ Ort", "Vorsteuerabzug"]
    )

    raw_name = anspruchsteller.get("Name", "")
    anrede, name_ohne_anrede = cleanup_person_name(raw_name)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = name_ohne_anrede
    data["MANDANT_STRASSE"] = anspruchsteller.get("Straße", "")
    data["MANDANT_PLZ_ORT"] = anspruchsteller.get("PLZ Ort", "")
    data["VORSTEUERBERECHTIGUNG"] = normalize_yes_no(anspruchsteller.get("Vorsteuerabzug", ""))

    # -------------------------
    # 2) Unfall
    # -------------------------
    unfall = parse_labeled_section(
        sections.get("Unfall", []),
        ["Datum", "Uhrzeit", "Ort", "Polizeilich erfasst", "Aktenzeichen Polizei", "Polizeibehörde"]
    )

    data["UNFALL_DATUM"] = first_regex(
        unfall.get("Datum", ""),
        [r"(\d{2}\.\d{2}\.\d{4})"]
    )

    unfall_ort_zeile = unfall.get("Ort", "")
    unfall_strasse, unfall_ort = split_street_and_place(unfall_ort_zeile)
    data["UNFALL_STRASSE"] = unfall_strasse
    data["UNFALL_ORT"] = unfall_ort or unfall_ort_zeile

    data["AKTENZEICHEN_POLIZEI"] = unfall.get("Aktenzeichen Polizei", "")
    data["POLIZEIBEHOERDE"] = unfall.get("Polizeibehörde", "")

    # -------------------------
    # 3) Unfallgegner
    # -------------------------
    unfallgegner = parse_labeled_section(
        sections.get("Unfallgegner", []),
        ["Kennzeichen"]
    )
    data["KENNZEICHEN"] = unfallgegner.get("Kennzeichen", "")

    # Fallback Kennzeichen aus Deckblatt / Freitext
    if not data["KENNZEICHEN"]:
        data["KENNZEICHEN"] = first_regex(
            full_text,
            [
                r"\b([A-ZÄÖÜ]{1,3}\s+[A-Z]{1,2}\s+\d{1,4})\b",
            ],
            flags=re.IGNORECASE
        )

    # -------------------------
    # 4) Versicherung
    # -------------------------
    versicherung = parse_labeled_section(
        sections.get("Versicherung", []),
        ["Name", "Straße", "PLZ Ort", "Telefon", "E-Mail", "Versicherungs-Nr.", "Versicherungs-Nr", "Schadennummer"]
    )

    data["VERSICHERUNG"] = versicherung.get("Name", "")
    data["VER_STRASSE"] = versicherung.get("Straße", "")
    data["VER_ORT"] = versicherung.get("PLZ Ort", "")

    data["SCHADENSNUMMER"] = (
        versicherung.get("Versicherungs-Nr.", "")
        or versicherung.get("Versicherungs-Nr", "")
        or versicherung.get("Schadennummer", "")
    )

    # -------------------------
    # 5) Haupt-Aktenzeichen vom Deckblatt
    # -------------------------
    data["AKTENZEICHEN"] = first_line_after(lines, "Aktenzeichen")
    if not data["AKTENZEICHEN"]:
        data["AKTENZEICHEN"] = data.get("AKTENZEICHEN_POLIZEI", "")

    # -------------------------
    # 6) Schadenhöhe / Reparatur / Fahrzeugwert
    # -------------------------
    schadenhoehe_lines = sections.get("Schadenhöhe", [])
    reparatur_lines = sections.get("Reparatur", [])
    fahrzeugwert_lines = sections.get("Fahrzeugwert", [])

    data["REPARATURKOSTEN_NETTO"] = money_from_labeled_lines(
        schadenhoehe_lines,
        ["Reparaturkosten ohne MwSt."]
    )

    data["WERTMINDERUNG"] = money_from_labeled_lines(
        schadenhoehe_lines,
        ["Merkantiler Minderwert", "Wertminderung"]
    )

    data["SCHADENHOEHE_OHNE_MWST"] = money_from_labeled_lines(
        schadenhoehe_lines,
        ["Schadenhöhe ohne MwSt."]
    )

    data["SCHADENHOEHE_INKL_MWST"] = money_from_labeled_lines(
        schadenhoehe_lines,
        ["Schadenhöhe inkl. MwSt."]
    )

    data["REPARATURKOSTEN_BRUTTO"] = money_from_labeled_lines(
        reparatur_lines,
        ["Reparaturkosten inkl. MwSt.", "Reparaturkosten brutto"]
    )

    data["WBW"] = money_from_labeled_lines(
        fahrzeugwert_lines,
        ["Wiederbeschaffungswert", "WBW"]
    )

    data["RESTWERT"] = money_from_labeled_lines(
        fahrzeugwert_lines,
        ["Restwert"]
    )

    data["WERTVERBESSERUNG"] = first_regex(
        full_text,
        [
            r"Wertverbesserung(?:\s*[:\-]|\s+)([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
    )
    data["WERTVERBESSERUNG"] = normalize_money_str(data["WERTVERBESSERUNG"])

    # -------------------------
    # 7) Gutachterkosten netto / brutto
    #    -> Labels hier breit angelegt, weil PDFs oft unterschiedlich heißen
    # -------------------------
    data["GUTACHTERKOSTEN_NETTO"] = first_regex(
        full_text,
        [
            r"(?:Gutachterkosten|Sachverständigenkosten|SV-Kosten|Honorar|Rechnungsbetrag|Endbetrag)\s*netto(?:\s*[:\-]|\s+)([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?:netto)\s*(?:Gutachterkosten|Sachverständigenkosten|SV-Kosten|Honorar|Rechnungsbetrag|Endbetrag)?(?:\s*[:\-]|\s+)([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
    )
    data["GUTACHTERKOSTEN_NETTO"] = normalize_money_str(data["GUTACHTERKOSTEN_NETTO"])

    data["GUTACHTERKOSTEN_BRUTTO"] = first_regex(
        full_text,
        [
            r"(?:Gutachterkosten|Sachverständigenkosten|SV-Kosten|Honorar|Rechnungsbetrag|Endbetrag)\s*(?:brutto|inkl\.?\s*MwSt\.?)(?:\s*[:\-]|\s+)([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})",
            r"(?:brutto|inkl\.?\s*MwSt\.?)\s*(?:Gutachterkosten|Sachverständigenkosten|SV-Kosten|Honorar|Rechnungsbetrag|Endbetrag)?(?:\s*[:\-]|\s+)([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})",
        ]
    )
    data["GUTACHTERKOSTEN_BRUTTO"] = normalize_money_str(data["GUTACHTERKOSTEN_BRUTTO"])

    # Fallback: nur ein allgemeiner Gutachterkosten-Wert vorhanden
    if not data["GUTACHTERKOSTEN_NETTO"] and not data["GUTACHTERKOSTEN_BRUTTO"]:
        generic_gutachter = first_regex(
            full_text,
            [
                r"(?:Gutachterkosten|Sachverständigenkosten|SV-Kosten)(?:\s*[:\-]|\s+)([+-]?\s*\d{1,3}(?:\.\d{3})*,\d{2})",
            ]
        )
        generic_gutachter = normalize_money_str(generic_gutachter)
        data["GUTACHTERKOSTEN_BRUTTO"] = generic_gutachter

    # -------------------------
    # 8) Fahrzeugtyp / Schadenhergang
    # -------------------------
    data["FAHRZEUGTYP"] = first_regex(
        full_text,
        [
            r"(?:Fahrzeugtyp|Fahrzeugart|Fahrzeug)\s*[:\-]?\s*([^\n]+)",
            r"(?:Hersteller\/Typ)\s*[:\-]?\s*([^\n]+)",
        ]
    )

    data["SCHADENHERGANG"] = first_regex(
        full_text,
        [
            r"(?:Schadenhergang|Unfallhergang)\s*[:\-]?\s*(.+?)(?=\n[A-ZÄÖÜ][^\n]{0,40}$|\Z)",
        ]
    )

    return data


def derive_gender_fields(anrede: str) -> Dict[str, str]:
    a = (anrede or "").strip().lower()

    if a == "frau":
        return {
            "GENDERN1": "ihrer",
            "GENDERN2": "meiner Mandantin",
            "GENDER1": "ihrer",
            "GENDER2": "meiner Mandantin",
        }

    if a == "herr":
        return {
            "GENDERN1": "seiner",
            "GENDERN2": "meines Mandanten",
            "GENDER1": "seiner",
            "GENDER2": "meines Mandanten",
        }

    return {
        "GENDERN1": "",
        "GENDERN2": "",
        "GENDER1": "",
        "GENDER2": "",
    }


def derive_fields(extracted: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}

    # Name
    vorname, nachname = split_first_last_name(str(extracted.get("MANDANT_NAME", "")))
    d["MANDANT_VORNAME"] = vorname
    d["MANDANT_NACHNAME"] = nachname

    # Gender-Platzhalter
    d.update(derive_gender_fields(str(extracted.get("MANDANT_ANREDE", ""))))

    # Vorsteuer
    vorsteuer = normalize_yes_no(str(extracted.get("VORSTEUERBERECHTIGUNG", "")))
    d["VORSTEUERBERECHTIGUNG"] = vorsteuer

    # Reparaturkosten: Annahme -> bei Ja netto, bei Nein brutto
    reparatur_netto = money_to_decimal(str(extracted.get("REPARATURKOSTEN_NETTO", "")))
    reparatur_brutto = money_to_decimal(str(extracted.get("REPARATURKOSTEN_BRUTTO", "")))

    if is_yes(vorsteuer):
        rep = reparatur_netto if reparatur_netto is not None else reparatur_brutto
    else:
        rep = reparatur_brutto if reparatur_brutto is not None else reparatur_netto

    d["REPARATURKOSTEN"] = format_decimal_de(rep) if rep is not None else ""

    # Wertminderung / Wertverbesserung
    wm = money_to_decimal(str(extracted.get("WERTMINDERUNG", ""))) or Decimal("0.00")
    wv = money_to_decimal(str(extracted.get("WERTVERBESSERUNG", ""))) or Decimal("0.00")

    d["WERTMINDERUNG"] = format_decimal_de(wm) if wm is not None else ""
    d["WERTVERBESSERUNG"] = format_decimal_de(wv) if wv is not None else ""

    # Kostenpauschale fix
    kp = Decimal("25.00")
    d["KOSTENPAUSCHALE"] = format_decimal_de(kp)

    # Gutachterkosten: bei Vorsteuer JA -> netto, sonst brutto
    gut_netto = money_to_decimal(str(extracted.get("GUTACHTERKOSTEN_NETTO", "")))
    gut_brutto = money_to_decimal(str(extracted.get("GUTACHTERKOSTEN_BRUTTO", "")))

    if is_yes(vorsteuer):
        gut = gut_netto if gut_netto is not None else gut_brutto
    else:
        gut = gut_brutto if gut_brutto is not None else gut_netto

    d["GUTACHTERKOSTEN"] = format_decimal_de(gut) if gut is not None else ""

    # Kostensumme:
    # Reparaturschaden + Wertminderung - Wertverbesserung + Kostenpauschale + Gutachterkosten
    total = Decimal("0.00")
    has_any = False

    for item in [rep, wm, kp, gut]:
        if item is not None:
            total += item
            has_any = True

    if wv is not None:
        total -= wv
        has_any = True

    d["KOSTENSUMME_X"] = format_decimal_de(total) if has_any else ""

    # Aliase / praktische Zusatzfelder
    d["REPARATURSCHADEN"] = d["REPARATURKOSTEN"]
    d["MANDANT_VOLLNAME"] = str(extracted.get("MANDANT_NAME", "")).strip()

    # Unfall-Ort fallback
    if not extracted.get("UNFALL_STRASSE") and extracted.get("UNFALL_ORT"):
        street, ort = split_street_and_place(str(extracted.get("UNFALL_ORT", "")))
        if street:
            d["UNFALL_STRASSE"] = street
            d["UNFALL_ORT"] = ort

    return d


def extract_from_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    text = pdf_to_text(pdf_bytes)
    extracted = extract_all(text)
    derived = derive_fields(extracted)
    return {**extracted, **derived}


def build_context_for_template(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}

    for key in template_keys:
        value = extracted.get(key, "")
        if value is None:
            value = ""
        ctx[key] = str(value)

    return ctx
