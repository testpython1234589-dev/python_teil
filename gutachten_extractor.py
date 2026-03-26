from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta
from typing import Dict, Any, Iterable, List, Tuple

try:
    import pymupdf as fitz
except ImportError:
    fitz = None

from pypdf import PdfReader


TITLE_PREFIXES = {"dr.", "dr", "prof.", "prof", "dipl.-ing.", "dipl.-ing", "ing.", "ing"}
SURNAME_JOINERS = {"von", "van", "de", "del", "der", "den", "zu", "zur", "zum", "al", "el", "abi", "bin", "ibn"}


def _clean_text(s: str) -> str:
    s = (s or "").replace("\xa0", " ").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def _pdf_to_pages_pymupdf(pdf_source: str | Path | bytes) -> List[str]:
    if fitz is None:
        return []

    if isinstance(pdf_source, (str, Path)):
        doc = fitz.open(str(pdf_source))
    else:
        doc = fitz.open(stream=pdf_source, filetype="pdf")

    pages: List[str] = []
    for page in doc:
        pages.append(_clean_text(page.get_text("text", sort=True)))
    return pages


def _pdf_to_pages_pypdf(pdf_source: str | Path | bytes) -> List[str]:
    if isinstance(pdf_source, (str, Path)):
        reader = PdfReader(str(pdf_source))
    else:
        reader = PdfReader(BytesIO(pdf_source))

    pages: List[str] = []
    for page in reader.pages:
        pages.append(_clean_text(page.extract_text() or ""))
    return pages


def pdf_to_pages(pdf_source: str | Path | bytes) -> List[str]:
    pages = _pdf_to_pages_pymupdf(pdf_source)
    if any(len(p) > 50 for p in pages):
        return pages
    return _pdf_to_pages_pypdf(pdf_source)


def pdf_to_text(pdf_source: str | Path | bytes) -> str:
    return "\f".join(pdf_to_pages(pdf_source))


def _split_pages(text: str) -> List[str]:
    pages = [_clean_text(p) for p in str(text).split("\f")]
    return [p for p in pages if p]


def _search_first(
    text: str,
    patterns: Iterable[str],
    flags: int = re.IGNORECASE | re.MULTILINE | re.DOTALL,
) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return _clean_text(m.group(1))
    return ""


def _find_page(pages: List[str], needles: Iterable[str], excludes: Iterable[str] = ()) -> str:
    for page in pages:
        page_lower = page.lower()
        if all(n.lower() in page_lower for n in needles) and not any(e.lower() in page_lower for e in excludes):
            return page
    return ""


def _parse_money(value: str) -> Decimal | None:
    if not value:
        return None

    raw = str(value).replace("€", "").replace("EUR", "")
    raw = raw.replace("\u202f", " ").replace("\xa0", " ")
    raw = re.sub(r"\s+", "", raw)

    m = re.search(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+(?:\.\d{2})", raw)
    if not m:
        return None

    raw = m.group(0)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _money_to_str(value: Decimal | None) -> str:
    if value is None:
        return ""
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def _extract_money(text: str, patterns: Iterable[str]) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if m:
            dec = _parse_money(m.group(1))
            if dec is not None:
                return _money_to_str(dec)
    return ""


def _cleanup_name(raw: str) -> tuple[str, str]:
    raw = _clean_text(raw)
    anrede = ""

    if re.match(r"(?i)^herr\b", raw):
        anrede = "Herr"
        raw = re.sub(r"(?i)^herr\b\.?\s*", "", raw).strip()
    elif re.match(r"(?i)^frau\b", raw):
        anrede = "Frau"
        raw = re.sub(r"(?i)^frau\b\.?\s*", "", raw).strip()

    return anrede, raw


def _split_name(full_name: str) -> tuple[str, str, str]:
    full_name = _clean_text(full_name)
    if not full_name:
        return "", "", ""

    tokens = full_name.split()

    titles: List[str] = []
    while tokens and tokens[0].lower() in TITLE_PREFIXES:
        titles.append(tokens.pop(0))

    titel = " ".join(titles).strip()

    if not tokens:
        return "", "", titel
    if len(tokens) == 1:
        return tokens[0], "", titel

    if len(tokens) >= 3 and tokens[-2].lower() in SURNAME_JOINERS:
        vorname = " ".join(tokens[:-2])
        nachname = " ".join(tokens[-2:])
    else:
        vorname = " ".join(tokens[:-1])
        nachname = tokens[-1]

    return vorname.strip(), nachname.strip(), titel


def _split_street_place(value: str) -> tuple[str, str]:
    value = _clean_text(value)
    if not value:
        return "", ""

    if "," in value:
        street, place = value.split(",", 1)
        return street.strip(), place.strip(" -")
    return value, ""


def _normalize_yes_no(value: str) -> str:
    v = _clean_text(value).lower()
    if v in {"ja", "yes", "y", "true", "1"}:
        return "Ja"
    if v in {"nein", "no", "n", "false", "0"}:
        return "Nein"
    return _clean_text(value)


def _gender_fields(anrede: str) -> Dict[str, str]:
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


def _extract_sonderkosten_from_pdf(pdf_source: str | Path | bytes) -> List[Dict[str, str]]:
    if fitz is None:
        return []

    if isinstance(pdf_source, (str, Path)):
        doc = fitz.open(str(pdf_source))
    else:
        doc = fitz.open(stream=pdf_source, filetype="pdf")

    for page in doc:
        page_text = _clean_text(page.get_text("text", sort=True))
        if "Sonderkosten" not in page_text or "Zusammenfassung" not in page_text:
            continue

        words = page.get_text("words")
        if not words:
            continue

        rows: Dict[float, List[Tuple[float, str]]] = {}
        for x0, y0, x1, y1, word, *_ in words:
            y_key = round(float(y0), 1)
            rows.setdefault(y_key, []).append((float(x0), str(word)))

        sorted_rows: List[Tuple[float, str]] = []
        for y, items in rows.items():
            items.sort(key=lambda t: t[0])
            line = " ".join(w for _, w in items)
            line = _clean_text(line)
            sorted_rows.append((y, line))

        sorted_rows.sort(key=lambda t: t[0])

        items: List[Dict[str, str]] = []
        in_block = False

        for _, line in sorted_rows:
            if not line:
                continue

            if "Sonderkosten" in line:
                in_block = True
                line_after_header = line.replace("Sonderkosten", "", 1).strip()
                if line_after_header:
                    m = re.match(r"(.+?)\s+([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})\s*€?$", line_after_header)
                    if m:
                        name = _clean_text(m.group(1))
                        betrag = _money_to_str(_parse_money(m.group(2)))
                        if name and betrag:
                            items.append({"name": name, "betrag": betrag})
                continue

            if in_block and (
                line.startswith("Nutzungsausfall")
                or line.startswith("Fahrzeugwert")
                or line.startswith("Reparatur")
                or line.startswith("Schadenhöhe")
            ):
                break

            if not in_block:
                continue

            m = re.match(r"(.+?)\s+([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2})\s*€?$", line)
            if not m:
                continue

            name = _clean_text(m.group(1))
            betrag = _money_to_str(_parse_money(m.group(2)))

            if name and betrag and name.lower() != "sonderkosten":
                items.append({"name": name, "betrag": betrag})

        return items

    return []


def _parse_gutachterexpress(pages: List[str], pdf_source: str | Path | bytes | None = None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data: Dict[str, Any] = {}

    p_bet = _find_page(pages, ["Beteiligte, Besichtigungen & Auftrag"])
    p_summary = _find_page(pages, ["Zusammenfassung", "Reparaturkosten ohne MwSt."], excludes=["Inhaltsverzeichnis"])
    p_invoice = _find_page(pages, ["Rechnung Nr.", "Gesamtbetrag ohne MwSt."])
    p_vehicle = _find_page(pages, ["Fahrzeugdaten", "Amtliches Kennzeichen"])
    p_sh = _find_page(pages, ["Schadenhergang", "Nach Angaben"], excludes=["Inhaltsverzeichnis"])
    p_wbw = _find_page(pages, ["Wiederbeschaffungswert"], excludes=["Inhaltsverzeichnis"])
    p_rest = _find_page(pages, ["Restwertermittlung"], excludes=["Inhaltsverzeichnis"])
    p_minder = _find_page(pages, ["Minderwertprotokoll"])

    p_calc = "\n".join(
        page for page in pages
        if (
            "R E P A R A T U R K O S T E N OHNE MWST" in page
            or "R E P A R A T U R K O S T E N MIT MWST" in page
            or "S C H L U S S K A L K U L A T I O N" in page
        )
    )

    raw_name = _search_first(
        p_bet,
        [
            r"Anspruchsteller Name\s+(.+?)\nStraße",
            r"Anspruchsteller\s+(.+?)\nStraße",
        ],
    ) or _search_first(
        full,
        [
            r"Anspruchsteller\s*\n(.+?)\nSachverständiger",
        ],
    )

    anrede, clean_name = _cleanup_name(raw_name)
    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name

    data["MANDANT_STRASSE"] = _search_first(
        p_bet,
        [r"Anspruchsteller Name\s+.+?\nStraße\s+(.+?)\nPLZ Ort"],
    )
    data["MANDANT_PLZ_ORT"] = _search_first(
        p_bet,
        [r"\nPLZ Ort\s+(.+?)\nVorsteuerabzug"],
    )
    data["VORSTEUERABZUG_RAW"] = _normalize_yes_no(
        _search_first(p_bet, [r"Vorsteuerabzug\s+(.+?)\nAnwalt"])
    )

    data["UNFALL_DATUM"] = _search_first(p_bet, [r"Unfall Datum\s+(\d{2}\.\d{2}\.\d{4})"])
    data["UNFALL_UHRZEIT"] = _search_first(p_bet, [r"Uhrzeit\s+(.+?)\nOrt"])

    unfall_ort_raw = _search_first(p_bet, [r"\nOrt\s+(.+?)\nPolizeilich erfasst"])
    unfall_strasse, unfall_ort = _split_street_place(unfall_ort_raw)
    data["UNFALL_STRASSE"] = unfall_strasse
    data["UNFALL_ORT"] = unfall_ort or unfall_ort_raw

    data["AKTENZEICHEN_POLIZEI"] = _search_first(p_bet, [r"Aktenzeichen Polizei\s+(.+?)\nPolizeibehörde"])
    data["POLIZEIBEHOERDE"] = _search_first(p_bet, [r"Polizeibehörde\s+(.+?)\nBesichtigung Datum"])

    data["KENNZEICHEN_GEGNER"] = _search_first(
        p_bet,
        [
            r"Unfallgegner.*?\nKennzeichen\s+(.+?)\n",
            r"Unfallgegner Kennzeichen\s+(.+?)\n",
            r"Kennzeichen\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,2}\s?\d{1,4})",
        ],
    )

    data["KENNZEICHEN_MANDANT"] = _search_first(p_vehicle, [r"Amtliches Kennzeichen\s+(.+?)\n"])
    data["KENNZEICHEN"] = data["KENNZEICHEN_GEGNER"]
    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    data["VERSICHERUNG"] = _search_first(
        p_bet,
        [r"Versicherung Name\s+(.+?)\n(?:Straße\s+.+?\n)?PLZ Ort"],
    )
    data["VER_STRASSE"] = _search_first(
        p_bet,
        [r"Versicherung Name\s+.+?\nStraße\s+(.+?)\nPLZ Ort"],
    )
    data["VER_ORT"] = _search_first(
        p_bet,
        [r"Versicherung Name\s+.+?\n(?:Straße\s+.+?\n)?PLZ Ort\s+(.+?)\nTelefon"],
    )

    data["SCHADENSNUMMER"] = _search_first(
        p_bet + "\n" + p_invoice,
        [
            r"Versicherungs-Nr\.?\s+([A-Z0-9\/\-]{6,})\b",
            r"Schadennummer\s+([A-Z0-9\/\-]{6,})\b",
        ],
    )

    data["AKTENZEICHEN"] = _search_first(
        full,
        [
            r"Rechnung Nr\.\s+([A-Z]{2,}-[A-Z]{2,}-\d{4}-\d{2}-\d+)",
            r"Aktenzeichen\s*\n(?:[A-Z]{1,4}[: ][A-Z]{1,4}\s*\d{1,4}\n)?([A-Z]{2,}-[A-Z]{2,}-\d{4}-\d{2}-\d+)",
            r"Aktenzeichen\s+([A-Z]{2,}-[A-Z]{2,}-\d{4}-\d{2}-\d+)",
        ],
    ) or data["AKTENZEICHEN_POLIZEI"]

    hersteller = _search_first(p_vehicle, [r"Hersteller\s+(.+?)\nModell"])
    modell = _search_first(p_vehicle, [r"Modell(?:/Haupttyp)?\s+(.+?)\n"])
    data["FAHRZEUGTYP"] = _clean_text(" ".join(x for x in [hersteller, modell] if x))

    data["SCHADENHERGANG"] = _search_first(p_sh, [r"Schadenhergang\s+(.+?)\nAnstoß-/Schadenbereich"])

    data["REPARATURKOSTEN_NETTO"] = _extract_money(
        p_summary + "\n" + p_calc,
        [
            r"Reparaturkosten ohne MwSt\.\s*([0-9\., ]+)",
            r"R E P A R A T U R K O S T E N OHNE MWST.*?([0-9][0-9\. ]+[0-9]\.[0-9]{2})",
        ],
    )
    data["REPARATURKOSTEN_BRUTTO"] = _extract_money(
        p_summary + "\n" + p_calc,
        [
            r"Reparatur(?: Reparaturkosten)? inkl\. MwSt\.[^\n]*?([0-9\., ]+)",
            r"R E P A R A T U R K O S T E N MIT MWST.*?([0-9][0-9\. ]+[0-9]\.[0-9]{2})",
        ],
    )
    data["WERTMINDERUNG"] = _extract_money(
        p_summary + "\n" + p_wbw + "\n" + p_minder,
        [
            r"Merkantiler Minderwert \(steuerneutral\)\s*\+?\s*([0-9\., ]+)",
            r"Minderwert:\s*([0-9\., ]+)",
            r"Vom Sachverständigen festgelegter Wert\s+([0-9\., ]+)",
        ],
    )
    data["WBW"] = _extract_money(
        p_summary + "\n" + p_wbw,
        [
            r"Wiederbeschaffungswert \(steuerneutral\)\s*([0-9\., ]+)",
            r"Wiederbeschaffungswert:\s*([0-9\., ]+)",
        ],
    )

    if re.search(r"Restwertermittlung\s*\(keine\)", p_rest, re.IGNORECASE):
        data["RESTWERT"] = ""
    else:
        data["RESTWERT"] = _extract_money(full, [r"Restwert(?:ermittlung)?[: ]+([0-9\., ]+)"])

    data["WERTVERBESSERUNG"] = _extract_money(full, [r"Wertverbesserung[: ]+([0-9\., ]+)"])
    data["GUTACHTERKOSTEN_NETTO"] = _extract_money(p_invoice, [r"Gesamtbetrag ohne MwSt\.\s*([0-9\., ]+)"])
    data["GUTACHTERKOSTEN_BRUTTO"] = _extract_money(p_invoice, [r"Gesamtbetrag inkl\. MwSt\.\s*([0-9\., ]+)"])

    sonderkosten_items = _extract_sonderkosten_from_pdf(pdf_source) if pdf_source is not None else []

    data["ABMELDEKOSTEN"] = ""
    data["UMMELDEKOSTEN"] = ""
    data["MELDUNGSKOSTEN_RAW"] = ""
    data["ZUSATZKOSTEN1_NAME"] = ""
    data["ZUSATZKOSTEN1_BETRAG"] = ""
    data["ZUSATZKOSTEN2_NAME"] = ""
    data["ZUSATZKOSTEN2_BETRAG"] = ""
    data["ZUSATZKOSTEN3_NAME"] = ""
    data["ZUSATZKOSTEN3_BETRAG"] = ""

    zusatz_index = 1
    for item in sonderkosten_items:
        name = item["name"]
        betrag = item["betrag"]
        name_lower = name.lower()

        if (
            "anmelde" in name_lower
            or "abmelde" in name_lower
            or "meldegebühr" in name_lower
            or "an- & abmelde" in name_lower
            or "ab- & anmelde" in name_lower
        ):
            data["MELDUNGSKOSTEN_RAW"] = betrag
            continue

        if zusatz_index <= 3:
            data[f"ZUSATZKOSTEN{zusatz_index}_NAME"] = name
            data[f"ZUSATZKOSTEN{zusatz_index}_BETRAG"] = betrag
            zusatz_index += 1

    return data


def _parse_generic(pages: List[str], pdf_source: str | Path | bytes | None = None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data: Dict[str, Any] = {}

    raw_name = _search_first(
        full,
        [
            r"Anspruchsteller(?: Name)?\s+(.+?)\n(?:Straße|PLZ Ort|Sachverständiger)",
            r"Geschädigt(?:e|er|en|e[rn])\s*[:\-]?\s*(.+?)\n",
        ],
    )
    anrede, clean_name = _cleanup_name(raw_name)
    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name

    data["MANDANT_STRASSE"] = _search_first(
        full,
        [
            r"Anspruchsteller(?: Name)?\s+.+?\nStraße\s+(.+?)\nPLZ Ort",
            r"\nStraße\s+(.+?)\nPLZ Ort",
        ],
    )
    data["MANDANT_PLZ_ORT"] = _search_first(
        full,
        [
            r"Anspruchsteller(?: Name)?\s+.+?\nStraße\s+.+?\nPLZ Ort\s+(.+?)\n",
            r"\nPLZ Ort\s+(.+?)\n",
        ],
    )
    data["VORSTEUERBERECHTIGUNG"] = _normalize_yes_no(
        _search_first(
            full,
            [
                r"Vorsteuerabzug\s+(.+?)\n",
                r"Vorsteuerabzugsberechtigt\s*[:\-]?\s*(.+?)\n",
            ],
        )
    )

    data["UNFALL_DATUM"] = _search_first(
        full,
        [
            r"Unfall Datum\s+(\d{2}\.\d{2}\.\d{4})",
            r"Schadentag\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
            r"Unfalldatum\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
        ],
    )

    unfall_ort_raw = _search_first(
        full,
        [
            r"\nOrt\s+(.+?)\nPolizeilich erfasst",
            r"Unfallort\s*[:\-]?\s*(.+?)\n",
            r"Schadenort\s*[:\-]?\s*(.+?)\n",
        ],
    )
    unfall_strasse, unfall_ort = _split_street_place(unfall_ort_raw)
    data["UNFALL_STRASSE"] = unfall_strasse
    data["UNFALL_ORT"] = unfall_ort or unfall_ort_raw

    data["AKTENZEICHEN_POLIZEI"] = _search_first(full, [r"Aktenzeichen Polizei\s+(.+?)\n"])
    data["AKTENZEICHEN"] = _search_first(
        full,
        [
            r"Rechnung Nr\.\s+([A-Z]{2,}-[A-Z]{2,}-\d{4}-\d{2}-\d+)",
            r"Aktenzeichen\s+([A-Z]{2,}-[A-Z]{2,}-\d{4}-\d{2}-\d+)",
            r"Aktenzeichen\s+(.+?)\n",
        ],
    ) or data["AKTENZEICHEN_POLIZEI"]

    data["KENNZEICHEN_GEGNER"] = _search_first(
        full,
        [
            r"Unfallgegner Kennzeichen\s+(.+?)\n",
            r"Gegner(?:fahrzeug)?\s+Kennzeichen\s+(.+?)\n",
        ],
    )
    data["KENNZEICHEN_MANDANT"] = _search_first(
        full,
        [
            r"Amtliches Kennzeichen\s+(.+?)\n",
            r"Kennzeichen Mandant\s*[:\-]?\s*(.+?)\n",
            r"Kennzeichen eigenes Fahrzeug\s*[:\-]?\s*(.+?)\n",
        ],
    )

    data["KENNZEICHEN"] = data["KENNZEICHEN_GEGNER"]
    data["EIGENES_KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]

    data["VERSICHERUNG"] = _search_first(
        full,
        [
            r"Versicherung Name\s+(.+?)\n",
            r"Versicherung\s*[:\-]?\s*(.+?)\n",
        ],
    )
    data["VER_STRASSE"] = _search_first(full, [r"Versicherung Name\s+.+?\nStraße\s+(.+?)\nPLZ Ort"])
    data["VER_ORT"] = _search_first(
        full,
        [
            r"Versicherung Name\s+.+?\nPLZ Ort\s+(.+?)\n",
            r"Versicherung.*?\nPLZ Ort\s+(.+?)\n",
        ],
    )
    data["SCHADENSNUMMER"] = _search_first(
        full,
        [
            r"Versicherungs-Nr\.?\s+(.+?)\n",
            r"Schadennummer\s*[:\-]?\s*(.+?)\n",
        ],
    )

    hersteller = _search_first(full, [r"Hersteller\s+(.+?)\n"])
    modell = _search_first(full, [r"Modell(?:/Haupttyp)?\s+(.+?)\n"])
    data["FAHRZEUGTYP"] = _clean_text(" ".join(x for x in [hersteller, modell] if x))

    data["SCHADENHERGANG"] = _search_first(
        full,
        [
            r"Schadenhergang\s+(.+?)\nAnstoß-/Schadenbereich",
            r"Schadenhergang\s+(.+?)\nSchadenbeschreibung",
            r"Unfallhergang\s+(.+?)\n",
        ],
    )

    data["REPARATURKOSTEN_NETTO"] = _extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.\s*([0-9\., ]+)",
            r"R E P A R A T U R K O S T E N OHNE MWST.*?([0-9][0-9\. ]+[0-9]\.[0-9]{2})",
        ],
    )
    data["REPARATURKOSTEN_BRUTTO"] = _extract_money(
        full,
        [
            r"Reparatur(?: Reparaturkosten)? inkl\. MwSt\.[^\n]*?([0-9\., ]+)",
            r"R E P A R A T U R K O S T E N MIT MWST.*?([0-9][0-9\. ]+[0-9]\.[0-9]{2})",
        ],
    )
    data["WERTMINDERUNG"] = _extract_money(
        full,
        [
            r"Merkantiler Minderwert(?: \(steuerneutral\))?\s*\+?\s*([0-9\., ]+)",
            r"Minderwert:\s*([0-9\., ]+)",
        ],
    )
    data["WBW"] = _extract_money(
        full,
        [
            r"Wiederbeschaffungswert(?: \(steuerneutral\))?\s*([0-9\., ]+)",
            r"Wiederbeschaffungswert:\s*([0-9\., ]+)",
        ],
    )

    if re.search(r"Restwertermittlung\s*\(keine\)", full, re.IGNORECASE):
        data["RESTWERT"] = ""
    else:
        data["RESTWERT"] = _extract_money(full, [r"Restwert(?:ermittlung)?[: ]+([0-9\., ]+)"])

    data["WERTVERBESSERUNG"] = _extract_money(full, [r"Wertverbesserung[: ]+([0-9\., ]+)"])
    data["GUTACHTERKOSTEN_NETTO"] = _extract_money(
        full,
        [
            r"Gesamtbetrag ohne MwSt\.\s*([0-9\., ]+)",
            r"Rechnungsbetrag ohne MwSt\.\s*([0-9\., ]+)",
        ],
    )
    data["GUTACHTERKOSTEN_BRUTTO"] = _extract_money(
        full,
        [
            r"Gesamtbetrag inkl\. MwSt\.\s*([0-9\., ]+)",
            r"Rechnungsbetrag inkl\. MwSt\.\s*([0-9\., ]+)",
        ],
    )

    sonderkosten_items = _extract_sonderkosten_from_pdf(pdf_source) if pdf_source is not None else []

    data["ABMELDEKOSTEN"] = ""
    data["UMMELDEKOSTEN"] = ""
    data["MELDUNGSKOSTEN_RAW"] = ""
    data["ZUSATZKOSTEN1_NAME"] = ""
    data["ZUSATZKOSTEN1_BETRAG"] = ""
    data["ZUSATZKOSTEN2_NAME"] = ""
    data["ZUSATZKOSTEN2_BETRAG"] = ""
    data["ZUSATZKOSTEN3_NAME"] = ""
    data["ZUSATZKOSTEN3_BETRAG"] = ""

    zusatz_index = 1
    for item in sonderkosten_items:
        name = item["name"]
        betrag = item["betrag"]
        name_lower = name.lower()

        if (
            "anmelde" in name_lower
            or "abmelde" in name_lower
            or "meldegebühr" in name_lower
            or "an- & abmelde" in name_lower
            or "ab- & anmelde" in name_lower
        ):
            data["MELDUNGSKOSTEN_RAW"] = betrag
            continue

        if zusatz_index <= 3:
            data[f"ZUSATZKOSTEN{zusatz_index}_NAME"] = name
            data[f"ZUSATZKOSTEN{zusatz_index}_BETRAG"] = betrag
            zusatz_index += 1

    return data


def extract_all(text: str, pdf_source: str | Path | bytes | None = None) -> Dict[str, Any]:
    pages = _split_pages(text)
    full = "\n".join(pages)

    if "GutachterExpress" in full and "Beteiligte, Besichtigungen & Auftrag" in full:
        data = _parse_gutachterexpress(pages, pdf_source=pdf_source)
        data["_PARSER"] = "gutachterexpress"
        return data

    data = _parse_generic(pages, pdf_source=pdf_source)
    data["_PARSER"] = "generic"
    return data


def derive_fields(extracted: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}

    vorname, nachname, titel = _split_name(str(extracted.get("MANDANT_NAME", "")))
    d["MANDANT_VORNAME"] = vorname
    d["MANDANT_NACHNAME"] = nachname
    d["MANDANT_TITEL"] = titel
    d["MANDANT_VOLLNAME"] = " ".join(x for x in [titel, vorname, nachname] if x).strip()

    gender = _gender_fields(str(extracted.get("MANDANT_ANREDE", "")))
    d.update(gender)

    vorsteuer_raw = _normalize_yes_no(str(extracted.get("VORSTEUERABZUG_RAW", extracted.get("VORSTEUERBERECHTIGUNG", ""))))
    d["VORSTEUERABZUG_RAW"] = vorsteuer_raw

    if vorsteuer_raw == "Ja":
        d["VORSTEUERBERECHTIGUNG"] = ""
    elif vorsteuer_raw == "Nein":
        d["VORSTEUERBERECHTIGUNG"] = "nicht"
    else:
        d["VORSTEUERBERECHTIGUNG"] = ""

    rep_net = _parse_money(str(extracted.get("REPARATURKOSTEN_NETTO", "")))
    rep_br = _parse_money(str(extracted.get("REPARATURKOSTEN_BRUTTO", "")))
    gut_net = _parse_money(str(extracted.get("GUTACHTERKOSTEN_NETTO", "")))
    gut_br = _parse_money(str(extracted.get("GUTACHTERKOSTEN_BRUTTO", "")))
    wm = _parse_money(str(extracted.get("WERTMINDERUNG", ""))) or Decimal("0")
    wv = _parse_money(str(extracted.get("WERTVERBESSERUNG", ""))) or Decimal("0")
    wbw = _parse_money(str(extracted.get("WBW", "")))
    restwert = _parse_money(str(extracted.get("RESTWERT", "")))
    meldung_raw = _parse_money(str(extracted.get("MELDUNGSKOSTEN_RAW", "")))
    zk1 = _parse_money(str(extracted.get("ZUSATZKOSTEN1_BETRAG", ""))) or Decimal("0")
    zk2 = _parse_money(str(extracted.get("ZUSATZKOSTEN2_BETRAG", ""))) or Decimal("0")
    zk3 = _parse_money(str(extracted.get("ZUSATZKOSTEN3_BETRAG", ""))) or Decimal("0")
    kp = Decimal("25.00")

    if vorsteuer_raw == "Ja":
        reparatur = rep_net if rep_net is not None else rep_br
        gutachter = gut_net if gut_net is not None else gut_br
    else:
        reparatur = rep_br if rep_br is not None else rep_net
        gutachter = gut_br if gut_br is not None else gut_net

    d["REPARATURKOSTEN"] = _money_to_str(reparatur)
    d["REPARATURSCHADEN"] = d["REPARATURKOSTEN"]
    d["GUTACHTERKOSTEN"] = _money_to_str(gutachter)
    d["WERTMINDERUNG"] = _money_to_str(wm)
    d["WERTVERBESSERUNG"] = _money_to_str(wv)
    d["WBW"] = _money_to_str(wbw)
    d["KOSTENPAUSCHALE"] = _money_to_str(kp)

    meldungskosten = meldung_raw or Decimal("0")
    d["MELDUNGSKOSTEN"] = _money_to_str(meldungskosten) if meldungskosten > 0 else ""

    d["ZUSATZKOSTEN_BEZEICHNUNG1"] = str(extracted.get("ZUSATZKOSTEN1_NAME", "") or "") if zk1 > 0 else ""
    d["ZUSATZKOSTEN_BETRAG1"] = _money_to_str(zk1) if zk1 > 0 else ""

    d["ZUSATZKOSTEN_BEZEICHNUNG2"] = str(extracted.get("ZUSATZKOSTEN2_NAME", "") or "") if zk2 > 0 else ""
    d["ZUSATZKOSTEN_BETRAG2"] = _money_to_str(zk2) if zk2 > 0 else ""

    d["ZUSATZKOSTEN_BEZEICHNUNG3"] = str(extracted.get("ZUSATZKOSTEN3_NAME", "") or "") if zk3 > 0 else ""
    d["ZUSATZKOSTEN_BETRAG3"] = _money_to_str(zk3) if zk3 > 0 else ""

    if wbw is not None and restwert is not None:
        wiederbeschaffungsaufwand = wbw - restwert
        d["WIEDERBESCHAFFUNGSWERTAUFWAND"] = _money_to_str(wiederbeschaffungsaufwand)
    elif wbw is not None:
        wiederbeschaffungsaufwand = wbw
        d["WIEDERBESCHAFFUNGSWERTAUFWAND"] = _money_to_str(wiederbeschaffungsaufwand)
    else:
        wiederbeschaffungsaufwand = Decimal("0")
        d["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""

    # 1) Summe für Reparaturschaden
    kostensumme_reparatur = (
        (reparatur or Decimal("0"))
        + wm
        - wv
        + kp
        + (gutachter or Decimal("0"))
    )
    d["KOSTENSUMME_REPARATUR"] = _money_to_str(kostensumme_reparatur)

    # 2) Summe für Totalschaden
    kostensumme_totalschaden = (
        wiederbeschaffungsaufwand
        + kp
        + (gutachter or Decimal("0"))
        + meldungskosten
        + zk1
        + zk2
        + zk3
    )
    d["KOSTENSUMME_TOTALSCHADEN"] = _money_to_str(kostensumme_totalschaden)

    # Standard-Fallback
    d["KOSTENSUMME_X"] = d["KOSTENSUMME_REPARATUR"]

    heute = datetime.now()
    frist = heute + timedelta(days=14)

    d["HEUTDATUM"] = heute.strftime("%d.%m.%Y")
    d["HEUTEDATUM"] = d["HEUTDATUM"]
    d["FRIST_DATUM"] = frist.strftime("%d.%m.%Y")
    d["FIRST_DATUM"] = d["FRIST_DATUM"]

    d["KENNZEICHEN_GEGNER"] = str(extracted.get("KENNZEICHEN_GEGNER") or extracted.get("KENNZEICHEN") or "")
    d["KENNZEICHEN_MANDANT"] = str(extracted.get("KENNZEICHEN_MANDANT") or extracted.get("EIGENES_KENNZEICHEN") or "")

    d["KENNZEICHEN"] = d["KENNZEICHEN_MANDANT"]
    d["EIGENES_KENNZEICHEN"] = d["KENNZEICHEN_MANDANT"]

    d["VRSICHERUNG"] = str(extracted.get("VERSICHERUNG", ""))
    d["GENDERN"] = gender.get("GENDERN1", "")
    d["GENDERN2"] = gender.get("GENDERN2", "")

    if wv > 0:
        d["WERTVERBESSERUNG_NAME"] = "Wertverbesserung"
        d["WERTBESSERUNG_BETRAG"] = _money_to_str(wv)
    else:
        d["WERTVERBESSERUNG_NAME"] = ""
        d["WERTBESSERUNG_BETRAG"] = ""

    if wm > 0:
        d["WERTMINDERUNG_NAME"] = "Wertminderung"
        d["WERTMINDERUNG_BETRAG"] = _money_to_str(wm)
    else:
        d["WERTMINDERUNG_NAME"] = ""
        d["WERTMINDERUNG_BETRAG"] = ""

    schadensnummer = str(extracted.get("SCHADENSNUMMER", "")).strip()
    m = re.search(r"[A-Z0-9\/\-]{6,}", schadensnummer)
    d["SCHADENSNUMMER"] = m.group(0) if m else ""

    return d


def extract_from_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    text = pdf_to_text(pdf_bytes)
    extracted = extract_all(text, pdf_source=pdf_bytes)
    derived = derive_fields(extracted)
    return {**extracted, **derived}


def build_context_for_template(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
    aliases = {
        "GESAMTSUMME": "KOSTENSUMME_X",
        "VRSICHERUNG": "VERSICHERUNG",
        "GENDERN": "GENDERN1",
        "KENNZEICHEN": "KENNZEICHEN_MANDANT",
        "EIGENES_KENNZEICHEN": "KENNZEICHEN_MANDANT",
        "HEUTDATUM": "HEUTEDATUM",
        "FIRST_DATUM": "FRIST_DATUM",
        "WIEDERBESCHAFFUNGSWERT": "WBW",
        "WIEDERBESCHAFFUNGSWERTAUFWAND": "WIEDERBESCHAFFUNGSWERTAUFWAND",
        "MELDUNGSKOSTEN": "MELDUNGSKOSTEN",
        "ZUSATZKOSTEN_BEZEICHNUNG1": "ZUSATZKOSTEN_BEZEICHNUNG1",
        "ZUSATZKOSTEN_BETRAG1": "ZUSATZKOSTEN_BETRAG1",
        "ZUSATZKOSTEN_BEZEICHNUNG2": "ZUSATZKOSTEN_BEZEICHNUNG2",
        "ZUSATZKOSTEN_BETRAG2": "ZUSATZKOSTEN_BETRAG2",
        "ZUSATZKOSTEN_BEZEICHNUNG3": "ZUSATZKOSTEN_BEZEICHNUNG3",
        "ZUSATZKOSTEN_BETRAG3": "ZUSATZKOSTEN_BETRAG3",
        "SCHADENNUMMER": "SCHADENSNUMMER",
    }

    now = datetime.now()
    heute_str = now.strftime("%d.%m.%Y")
    frist_str = (now + timedelta(days=14)).strftime("%d.%m.%Y")

    defaults = {
        "HEUTDATUM": heute_str,
        "HEUTEDATUM": heute_str,
        "FRIST_DATUM": frist_str,
        "FIRST_DATUM": frist_str,
    }

        is_totalschaden_template = (
        "WIEDERBESCHAFFUNGSWERTAUFWAND" in template_keys
        or "MELDUNGSKOSTEN" in template_keys
        or "ZUSATZKOSTEN_BEZEICHNUNG1" in template_keys
    )

    ctx: Dict[str, Any] = {}
    for key in template_keys:
        value = extracted.get(key)

        if key == "KOSTENSUMME_X":
            if is_totalschaden_template:
                value = extracted.get("KOSTENSUMME_TOTALSCHADEN", extracted.get("KOSTENSUMME_X", ""))
            else:
                value = extracted.get("KOSTENSUMME_REPARATUR", extracted.get("KOSTENSUMME_X", ""))

        if value in (None, "") and key in aliases:
            value = extracted.get(aliases[key], "")

        if value in (None, "") and key in defaults:
            value = defaults[key]

        ctx[key] = "" if value is None else str(value)
    if "SCHADENSNUMMER" not in ctx and extracted.get("SCHADENSNUMMER"):
        ctx["SCHADENSNUMMER"] = str(extracted.get("SCHADENSNUMMER"))

    return ctx
