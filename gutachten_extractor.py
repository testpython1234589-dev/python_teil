from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Iterable

from pypdf import PdfReader


TITLE_PREFIXES = {"dr.", "dr", "prof.", "prof", "dipl.-ing.", "dipl.-ing", "ing.", "ing"}
SURNAME_JOINERS = {"von", "van", "de", "del", "der", "den", "zu", "zur", "zum", "al", "el", "abi", "bin", "ibn"}


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
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def search_first(text: str, patterns: Iterable[str], flags=re.IGNORECASE | re.MULTILINE | re.DOTALL) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return norm_spaces(m.group(1))
    return ""


def parse_money(value: str) -> Decimal | None:
    if not value:
        return None

    raw = value.strip().replace("€", "").replace("EUR", "")
    raw = raw.replace("\u202f", " ").replace("\xa0", " ")
    raw = re.sub(r"\s+", "", raw)

    # 1.234,56
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", raw):
        raw = raw.replace(".", "").replace(",", ".")
    # 2545.31
    elif re.fullmatch(r"-?\d+(?:\.\d{2})?", raw):
        pass
    # 2545,31
    elif re.fullmatch(r"-?\d+,\d{2}", raw):
        raw = raw.replace(",", ".")
    else:
        m = re.search(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+(?:\.\d{2})", raw)
        if not m:
            return None
        return parse_money(m.group(0))

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def money_to_str(value: Decimal | None) -> str:
    if value is None:
        return ""
    s = f"{value:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def extract_money(text: str, patterns: Iterable[str]) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if not m:
            continue
        dec = parse_money(m.group(1))
        if dec is not None:
            return money_to_str(dec)
    return ""


def cleanup_name(raw: str) -> tuple[str, str]:
    raw = norm_spaces(raw)
    if not raw:
        return "", ""

    anrede = ""
    if re.match(r"(?i)^herr\b", raw):
        anrede = "Herr"
        raw = re.sub(r"(?i)^herr\b\.?\s*", "", raw).strip()
    elif re.match(r"(?i)^frau\b", raw):
        anrede = "Frau"
        raw = re.sub(r"(?i)^frau\b\.?\s*", "", raw).strip()

    return anrede, raw


def split_name(full_name: str) -> tuple[str, str, str]:
    full_name = norm_spaces(full_name)
    if not full_name:
        return "", "", ""

    tokens = full_name.split()

    title_tokens = []
    while tokens and tokens[0].lower() in TITLE_PREFIXES:
        title_tokens.append(tokens.pop(0))

    titel = " ".join(title_tokens).strip()

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


def split_street_place(value: str) -> tuple[str, str]:
    value = norm_spaces(value)
    if not value:
        return "", ""

    if "," in value:
        street, rest = value.split(",", 1)
        return street.strip(), rest.strip(" -")
    return value, ""


def normalize_yes_no(value: str) -> str:
    v = norm_spaces(value).lower()
    if v in {"ja", "yes", "y", "true", "1"}:
        return "Ja"
    if v in {"nein", "no", "n", "false", "0"}:
        return "Nein"
    return norm_spaces(value)


def gender_fields(anrede: str) -> Dict[str, str]:
    a = anrede.lower()
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


def extract_all(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    txt = text

    # Mandant
    claimant_name = search_first(
        txt,
        [
            r"Beteiligte, Besichtigungen & Auftrag.*?Name\s+([^\n]+?)\s*\nStraße\s+[^\n]+\s*\nPLZ Ort\s+[^\n]+\s*\nAnspruchsteller\b",
            r"Anspruchsteller\s*\n([^\n]+)",
            r"Geschädigt(?:e|er|en|e[rn])\s*[:\-]?\s*([^\n]+)",
            r"Anspruchsteller\s*[:\-]?\s*([^\n]+)",
        ],
    )
    anrede, name_ohne_anrede = cleanup_name(claimant_name)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = name_ohne_anrede
    data["MANDANT_STRASSE"] = search_first(
        txt,
        [
            r"Beteiligte, Besichtigungen & Auftrag.*?Name\s+[^\n]+\s*\nStraße\s+([^\n]+?)\s*\nPLZ Ort\s+[^\n]+\s*\nAnspruchsteller\b",
            r"Anspruchsteller.*?Straße\s*[:\-]?\s*([^\n]+)",
            r"Geschädigt(?:e|er|en|e[rn]).*?\nStraße\s*[:\-]?\s*([^\n]+)",
        ],
    )
    data["MANDANT_PLZ_ORT"] = search_first(
        txt,
        [
            r"Beteiligte, Besichtigungen & Auftrag.*?Straße\s+[^\n]+\s*\nPLZ Ort\s+([^\n]+?)\s*\nAnspruchsteller\b",
            r"Anspruchsteller.*?PLZ Ort\s*[:\-]?\s*([^\n]+)",
            r"\n(\d{5}\s+[^\n]+)\nZusammenfassung",
        ],
    )
    data["VORSTEUERBERECHTIGUNG"] = normalize_yes_no(
        search_first(
            txt,
            [
                r"Anspruchsteller\s*\nVorsteuerabzug\s+([^\n]+)",
                r"Vorsteuerabzug\s*[:\-]?\s*([^\n]+)",
                r"Vorsteuerabzugsberechtigt\s*[:\-]?\s*([^\n]+)",
            ],
        )
    )

    # Unfall
    data["UNFALL_DATUM"] = search_first(
        txt,
        [
            r"Unfall\s+Datum\s+(\d{2}\.\d{2}\.\d{4})",
            r"Schadentag\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
            r"Unfalldatum\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
        ],
    )
    data["UNFALL_UHRZEIT"] = search_first(
        txt,
        [
            r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\nUhrzeit\s+([^\n]+)",
            r"Uhrzeit\s*[:\-]?\s*([^\n]+)",
        ],
    )

    unfall_ort_raw = search_first(
        txt,
        [
            r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}\s*\nUhrzeit\s+[^\n]+\s*\nOrt\s+([^\n]+)",
            r"Unfallort\s*[:\-]?\s*([^\n]+)",
            r"Schadenort\s*[:\-]?\s*([^\n]+)",
        ],
    )
    street, place = split_street_place(unfall_ort_raw)
    data["UNFALL_STRASSE"] = street
    data["UNFALL_ORT"] = place or unfall_ort_raw

    data["AKTENZEICHEN_POLIZEI"] = search_first(
        txt,
        [
            r"Aktenzeichen Polizei\s+([^\n]+)",
            r"Polizeiaktenzeichen\s*[:\-]?\s*([^\n]+)",
        ],
    )
    data["POLIZEIBEHOERDE"] = search_first(
        txt,
        [
            r"Polizeibehörde\s+(.+?)(?=\nDatum\s+\d{2}\.\d{2}\.\d{4}|\nBesichtigung\b|\nUnfallgegner\b|\nVersicherung\b|\nAuftrag\b)",
            r"Polizeibehörde\s*[:\-]?\s*([^\n]+)",
        ],
    )

    # Aktenzeichen
    data["AKTENZEICHEN"] = search_first(
        txt,
        [
            r"Aktenzeichen\s*\n([A-Z0-9\-\/]+)",
            r"Vorgangsnummer\s*[:\-]?\s*([A-Z0-9\-\/]+)",
        ],
    ) or data["AKTENZEICHEN_POLIZEI"]

    # Kennzeichen Gegner / eigenes Fahrzeug
    data["KENNZEICHEN"] = search_first(
        txt,
        [
            r"Unfallgegner\s+Kennzeichen\s+([^\n]+)",
            r"Gegner(?:fahrzeug)?\s+Kennzeichen\s*[:\-]?\s*([^\n]+)",
        ],
    )
    data["EIGENES_KENNZEICHEN"] = search_first(
        txt,
        [
            r"Amtliches Kennzeichen\s+([^\n]+)",
            r"Kennzeichen\s+([A-ZÄÖÜ]{1,4}\s?[A-Z]{1,2}\s?\d{1,4})",
        ],
    )

    # Versicherung
    data["VERSICHERUNG"] = search_first(
        txt,
        [
            r"Unfallgegner\s+Kennzeichen\s+[^\n]+\s*\nName\s+([^\n]+?)\s*\n(?:Straße\s+[^\n]+\s*\n)?PLZ Ort\s+[^\n]+\s*\nTelefon\s+[^\n]+\s*\nE-Mail\s+[^\n]+\s*\nVersicherung\b",
            r"Versicherung\s*[:\-]?\s*([^\n]+)",
            r"gegnerische Versicherung\s*[:\-]?\s*([^\n]+)",
        ],
    )
    data["VER_STRASSE"] = search_first(
        txt,
        [
            r"Versicherung.*?\nStraße\s+([^\n]+)",
            r"gegnerische Versicherung.*?\nStraße\s+([^\n]+)",
        ],
    )
    data["VER_ORT"] = search_first(
        txt,
        [
            r"Unfallgegner\s+Kennzeichen\s+[^\n]+\s*\nName\s+[^\n]+\s*\n(?:Straße\s+[^\n]+\s*\n)?PLZ Ort\s+([^\n]+)",
            r"Versicherung.*?\nPLZ Ort\s+([^\n]+)",
            r"Versicherung.*?\n(?:Straße\s+[^\n]+\n)?(\d{5}\s+[^\n]+)",
        ],
    )
    data["SCHADENSNUMMER"] = search_first(
        txt,
        [
            r"Versicherungs-Nr\.\s+([^\n]+)",
            r"Versicherungs-Nr\s+([^\n]+)",
            r"Schadennummer\s*[:\-]?\s*([^\n]+)",
        ],
    )

    # Fahrzeugtyp
    hersteller = search_first(txt, [r"Hersteller\s+([^\n]+)"])
    modell = search_first(txt, [r"Modell(?:/Haupttyp)?\s+([^\n]+)"])
    fahrzeugtyp = " ".join([x for x in [hersteller, modell] if x]).strip()
    data["FAHRZEUGTYP"] = fahrzeugtyp or search_first(
        txt,
        [
            r"Fahrzeug\s*[:\-]?\s*([^\n]+)",
            r"Hersteller\/Typ\s*[:\-]?\s*([^\n]+)",
        ],
    )

    # Schadenhergang
    data["SCHADENHERGANG"] = search_first(
        txt,
        [
            r"Schadenhergang\s+(.+?)(?=\nAnstoß-/Schadenbereich|\nSchadenbeschreibung|\nPlausibilität|\nInstandsetzungskosten)",
            r"Unfallhergang\s+(.+?)(?=\nAnstoß-/Schadenbereich|\nSchadenbeschreibung|\nPlausibilität|\nInstandsetzungskosten)",
        ],
    )

    # Geldwerte
    data["REPARATURKOSTEN_NETTO"] = extract_money(
        txt,
        [
            r"Reparaturkosten ohne MwSt\.\s*([0-9\., ]+)",
            r"R E P A R A T U R K O S T E N OHNE MWST.*?([0-9][0-9\., ]+)",
        ],
    )
    data["REPARATURKOSTEN_BRUTTO"] = extract_money(
        txt,
        [
            r"Reparatur(?: Reparaturkosten)? inkl\. MwSt\.[^\n]*?([0-9\., ]+)\s*€",
            r"R E P A R A T U R K O S T E N MIT MWST.*?([0-9][0-9\., ]+)",
        ],
    )
    data["WERTMINDERUNG"] = extract_money(
        txt,
        [
            r"Merkantiler Minderwert(?: \(steuerneutral\))?\s*\+?\s*([0-9\., ]+)",
            r"Minderwert\s*[:\-]?\s*([0-9\., ]+)",
            r"vom SV festgelegter Minderwert.*?\n([0-9\., ]+)\s*€",
        ],
    )
    data["WBW"] = extract_money(
        txt,
        [
            r"Wiederbeschaffungswert(?: \(steuerneutral\))?\s*[:\-]?\s*([0-9\., ]+)",
            r"Fahrzeugwert Wiederbeschaffungswert(?: \(steuerneutral\))?\s*([0-9\., ]+)",
        ],
    )

    if re.search(r"Restwertermittlung\s*\(keine\)", txt, re.IGNORECASE):
        data["RESTWERT"] = ""
    else:
        data["RESTWERT"] = extract_money(
            txt,
            [
                r"Restwert\s*[:\-]?\s*([0-9\., ]+)",
                r"Veräußerungswert\s*([0-9\., ]+)",
            ],
        )

    data["WERTVERBESSERUNG"] = extract_money(
        txt,
        [
            r"Wertverbesserung\s*[:\-]?\s*([0-9\., ]+)",
        ],
    )

    # Gutachterkosten aus Rechnung
    data["GUTACHTERKOSTEN_NETTO"] = extract_money(
        txt,
        [
            r"Gesamtbetrag ohne MwSt\.\s*([0-9\., ]+)",
            r"Rechnungsbetrag ohne MwSt\.\s*([0-9\., ]+)",
        ],
    )
    data["GUTACHTERKOSTEN_BRUTTO"] = extract_money(
        txt,
        [
            r"Gesamtbetrag inkl\. MwSt\.\s*([0-9\., ]+)",
            r"Rechnungsbetrag inkl\. MwSt\.\s*([0-9\., ]+)",
        ],
    )

    return data


def derive_fields(extracted: Dict[str, Any]) -> Dict[str, Any]:
    d: Dict[str, Any] = {}

    vorname, nachname, titel = split_name(str(extracted.get("MANDANT_NAME", "")))
    d["MANDANT_VORNAME"] = vorname
    d["MANDANT_NACHNAME"] = nachname
    d["MANDANT_TITEL"] = titel
    d["MANDANT_VOLLNAME"] = " ".join(x for x in [titel, vorname, nachname] if x).strip()

    d.update(gender_fields(str(extracted.get("MANDANT_ANREDE", ""))))

    vorsteuer = normalize_yes_no(str(extracted.get("VORSTEUERBERECHTIGUNG", "")))
    d["VORSTEUERBERECHTIGUNG"] = vorsteuer

    rep_net = parse_money(str(extracted.get("REPARATURKOSTEN_NETTO", "")))
    rep_br = parse_money(str(extracted.get("REPARATURKOSTEN_BRUTTO", "")))
    gut_net = parse_money(str(extracted.get("GUTACHTERKOSTEN_NETTO", "")))
    gut_br = parse_money(str(extracted.get("GUTACHTERKOSTEN_BRUTTO", "")))
    wm = parse_money(str(extracted.get("WERTMINDERUNG", ""))) or Decimal("0")
    wv = parse_money(str(extracted.get("WERTVERBESSERUNG", ""))) or Decimal("0")
    kp = Decimal("25.00")

    if vorsteuer == "Ja":
        reparatur = rep_net if rep_net is not None else rep_br
        gutachter = gut_net if gut_net is not None else gut_br
    else:
        reparatur = rep_br if rep_br is not None else rep_net
        gutachter = gut_br if gut_br is not None else gut_net

    d["REPARATURKOSTEN"] = money_to_str(reparatur)
    d["REPARATURSCHADEN"] = d["REPARATURKOSTEN"]
    d["GUTACHTERKOSTEN"] = money_to_str(gutachter)
    d["WERTMINDERUNG"] = money_to_str(wm)
    d["WERTVERBESSERUNG"] = money_to_str(wv)
    d["KOSTENPAUSCHALE"] = money_to_str(kp)

    total = Decimal("0")
    for item in (reparatur, wm, gutachter):
        if item is not None:
            total += item

    total = total - wv + kp
    d["KOSTENSUMME_X"] = money_to_str(total)

    if not extracted.get("UNFALL_STRASSE") and extracted.get("UNFALL_ORT"):
        street, ort = split_street_place(str(extracted.get("UNFALL_ORT", "")))
        if street:
            d["UNFALL_STRASSE"] = street
            d["UNFALL_ORT"] = ort or street

    return d


def extract_from_pdf_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    text = pdf_to_text(pdf_bytes)
    extracted = extract_all(text)
    derived = derive_fields(extracted)
    return {**extracted, **derived}


def build_context_for_template(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {}
    aliases = {
        "GESAMTSUMME": "KOSTENSUMME_X",
    }

    for key in template_keys:
        value = extracted.get(key)
        if value in (None, "") and key in aliases:
            value = extracted.get(aliases[key], "")
        ctx[key] = "" if value is None else str(value)

    return ctx
