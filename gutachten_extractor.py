from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Iterable, List
from datetime import date, datetime, timedelta


try:
    import pymupdf as fitz  # preferred
except ImportError:  # pragma: no cover
    fitz = None

from pypdf import PdfReader


TITLE_PREFIXES = {"dr.", "dr", "prof.", "prof", "dipl.-ing.", "dipl.-ing", "ing.", "ing"}
SURNAME_JOINERS = {"von", "van", "de", "del", "der", "den", "zu", "zur", "zum", "al", "el", "abi", "bin", "ibn"}
heute=date.today()
HEUTEDATUM = heute.strftime("%d.%m.%Y")
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
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


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


def _parse_gutachterexpress(pages: List[str]) -> Dict[str, Any]:
    full = "\n".join(pages)
    data: Dict[str, Any] = {}

    p_bet = _find_page(pages, ["Beteiligte, Besichtigungen & Auftrag"])
    p_summary = _find_page(pages, ["Zusammenfassung", "Reparaturkosten ohne MwSt."], excludes=["Inhaltsverzeichnis"])
    p_invoice = _find_page(pages, ["Rechnung Nr.", "Gesamtbetrag ohne MwSt."])
    p_vehicle = _find_page(pages, ["Fahrzeugdaten", "Amtliches Kennzeichen"])
    p_sh = _find_page(pages, ["Schadenhergang\nNach Angaben"], excludes=["Inhaltsverzeichnis"])
    p_wbw = _find_page(pages, ["Wiederbeschaffungswert", "Minderwert:"], excludes=["Inhaltsverzeichnis"])
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
    data["VORSTEUERBERECHTIGUNG"] = _normalize_yes_no(
        _search_first(
            p_bet,
            [r"Vorsteuerabzug\s+(.+?)\nAnwalt"],
        )
    )

    data["UNFALL_DATUM"] = _search_first(
        p_bet,
        [r"Unfall Datum\s+(\d{2}\.\d{2}\.\d{4})"],
    )
    data["UNFALL_UHRZEIT"] = _search_first(
        p_bet,
        [r"Uhrzeit\s+(.+?)\nOrt"],
    )
    unfall_ort_raw = _search_first(
        p_bet,
        [r"\nOrt\s+(.+?)\nPolizeilich erfasst"],
    )
    unfall_strasse, unfall_ort = _split_street_place(unfall_ort_raw)
    data["UNFALL_STRASSE"] = unfall_strasse
    data["UNFALL_ORT"] = unfall_ort or unfall_ort_raw

    data["AKTENZEICHEN_POLIZEI"] = _search_first(
        p_bet,
        [r"Aktenzeichen Polizei\s+(.+?)\nPolizeibehörde"],
    )
    data["POLIZEIBEHOERDE"] = _search_first(
        p_bet,
        [r"Polizeibehörde\s+(.+?)\nBesichtigung Datum"],
    )

    data["KENNZEICHEN_GEGNER"] = _search_first(
    p_bet,
    [
        r"Unfallgegner Kennzeichen\s+(.+?)\nVersicherung Name",
        r"Unfallgegner Kennzeichen\s+(.+?)\nName",
    ],
)

data["KENNZEICHEN_MANDANT"] = _search_first(
    p_vehicle,
    [
        r"Amtliches Kennzeichen\s+(.+?)\n",
    ],
)

    # Rückwärtskompatibilität für alte Vorlagen
    data["KENNZEICHEN_GEGNER"] = data["KENNZEICHEN_GEGNER"]
    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
        
    data["VERSICHERUNG"] = _search_first(
        p_bet,
        [r"Versicherung Name\s+(.+?)\nPLZ Ort"],
    )
    data["VER_STRASSE"] = _search_first(
        p_bet,
        [r"Versicherung Name\s+.+?\nStraße\s+(.+?)\nPLZ Ort"],
    )
    data["VER_ORT"] = _search_first(
        p_bet,
        [r"Versicherung Name\s+.+?\nPLZ Ort\s+(.+?)\nTelefon"],
    )
    data["SCHADENSNUMMER"] = _search_first(
        p_bet,
        [r"Versicherungs-Nr\.?\s+(.+?)\nAuftrag Datum"],
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
    data["EIGENES_KENNZEICHEN"] = _search_first(
        p_vehicle,
        [r"Amtliches Kennzeichen\s+(.+?)\n"],
    )

    data["SCHADENHERGANG"] = _search_first(
        p_sh,
        [r"Schadenhergang\s+(.+?)\nAnstoß-/Schadenbereich"],
    )

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
        data["RESTWERT"] = _extract_money(
            full,
            [r"Restwert(?:ermittlung)?[: ]+([0-9\., ]+)"],
        )

    data["WERTVERBESSERUNG"] = _extract_money(
        full,
        [r"Wertverbesserung[: ]+([0-9\., ]+)"],
    )

    data["GUTACHTERKOSTEN_NETTO"] = _extract_money(
        p_invoice,
        [r"Gesamtbetrag ohne MwSt\.\s*([0-9\., ]+)"],
    )
    data["GUTACHTERKOSTEN_BRUTTO"] = _extract_money(
        p_invoice,
        [r"Gesamtbetrag inkl\. MwSt\.\s*([0-9\., ]+)"],
    )

    return data


def _parse_generic(pages: List[str]) -> Dict[str, Any]:
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

    data["AKTENZEICHEN_POLIZEI"] = _search_first(
        full,
        [r"Aktenzeichen Polizei\s+(.+?)\n"],
    )
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
    
    # Rückwärtskompatibilität
    
    data["KENNZEICHEN"] = data["KENNZEICHEN_MANDANT"]
        data["VERSICHERUNG"] = _search_first(
            full,
            [
                r"Versicherung Name\s+(.+?)\n",
                r"Versicherung\s*[:\-]?\s*(.+?)\n",
            ],
        )
        data["VER_STRASSE"] = _search_first(
            full,
            [r"Versicherung Name\s+.+?\nStraße\s+(.+?)\nPLZ Ort"],
        )
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
        data["RESTWERT"] = _extract_money(
            full,
            [r"Restwert(?:ermittlung)?[: ]+([0-9\., ]+)"],
        )

    data["WERTVERBESSERUNG"] = _extract_money(
        full,
        [r"Wertverbesserung[: ]+([0-9\., ]+)"],
    )

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

    return data


def extract_all(text: str) -> Dict[str, Any]:
    pages = _split_pages(text)
    full = "\n".join(pages)

    if "GutachterExpress" in full and "Beteiligte, Besichtigungen & Auftrag" in full:
        data = _parse_gutachterexpress(pages)
        data["_PARSER"] = "gutachterexpress"
        return data

    data = _parse_generic(pages)
    data["_PARSER"] = "generic"
    return data


def derive_fields(extracted: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}

    vorname, nachname, titel = _split_name(str(extracted.get("MANDANT_NAME", "")))
    d["MANDANT_VORNAME"] = vorname
    d["MANDANT_NACHNAME"] = nachname
    d["MANDANT_TITEL"] = titel
    d["MANDANT_VOLLNAME"] = " ".join(x for x in [titel, vorname, nachname] if x).strip()

    d.update(_gender_fields(str(extracted.get("MANDANT_ANREDE", ""))))

    vorsteuer = _normalize_yes_no(str(extracted.get("VORSTEUERBERECHTIGUNG", "")))
    d["VORSTEUERBERECHTIGUNG"] = vorsteuer

    rep_net = _parse_money(str(extracted.get("REPARATURKOSTEN_NETTO", "")))
    rep_br = _parse_money(str(extracted.get("REPARATURKOSTEN_BRUTTO", "")))
    gut_net = _parse_money(str(extracted.get("GUTACHTERKOSTEN_NETTO", "")))
    gut_br = _parse_money(str(extracted.get("GUTACHTERKOSTEN_BRUTTO", "")))
    wm = _parse_money(str(extracted.get("WERTMINDERUNG", ""))) or Decimal("0")
    wv = _parse_money(str(extracted.get("WERTVERBESSERUNG", ""))) or Decimal("0")
    kp = Decimal("25.00")

    if vorsteuer == "Ja":
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
    d["KOSTENPAUSCHALE"] = _money_to_str(kp)

    total = (reparatur or Decimal("0")) + wm - wv + kp + (gutachter or Decimal("0"))
    d["KOSTENSUMME_X"] = _money_to_str(total)

        # Datumsfelder für Word
    heute = datetime.now()
    frist = heute + timedelta(days=14)

    d["HEUTEDATUM"] = heute.strftime("%d.%m.%Y")
    d["FRIST_DATUM"] = frist.strftime("%d.%m.%Y")
        d["KENNZEICHEN_GEGNER"] = str(
        extracted.get("KENNZEICHEN_GEGNER")
        or extracted.get("KENNZEICHEN")
        or ""
    )

    d["KENNZEICHEN_MANDANT"] = str(
        extracted.get("KENNZEICHEN_MANDANT")
        or extracted.get("EIGENES_KENNZEICHEN")
        or ""
    )

    # Alte Felder weiter unterstützen
    d["KENNZEICHEN"] = d["KENNZEICHEN_GEGNER"]
    d["EIGENES_KENNZEICHEN"] = d["KENNZEICHEN_MANDANT"]

    return d


def extract_from_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    text = pdf_to_text(pdf_bytes)
    extracted = extract_all(text)
    derived = derive_fields(extracted)
    return {**extracted, **derived}


def build_context_for_template(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
     aliases = {
    "GESAMTSUMME": "KOSTENSUMME_X",
    "KENNZEICHEN": "KENNZEICHEN_GEGNER",
    "EIGENES_KENNZEICHEN": "KENNZEICHEN_MANDANT",
}

    ctx: Dict[str, Any] = {}
    for key in template_keys:
        value = extracted.get(key)

        if value in (None, "") and key in aliases:
            value = extracted.get(aliases[key], "")

        ctx[key] = "" if value is None else str(value)

    return ctx
