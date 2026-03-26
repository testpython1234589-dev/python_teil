from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Dict, Tuple, Any

try:
    import pymupdf as fitz
except ImportError:
    fitz = None

from pypdf import PdfReader


TITLE_PREFIXES = {"dr.", "dr", "prof.", "prof", "dipl.-ing.", "dipl.-ing", "ing.", "ing"}
SURNAME_JOINERS = {"von", "van", "de", "del", "der", "den", "zu", "zur", "zum", "al", "el", "abi", "bin", "ibn"}


def clean_text(s: str) -> str:
    s = (s or "").replace("\xa0", " ").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def pdf_to_pages_pymupdf(pdf_source: str | Path | bytes) -> List[str]:
    if fitz is None:
        return []

    if isinstance(pdf_source, (str, Path)):
        doc = fitz.open(str(pdf_source))
    else:
        doc = fitz.open(stream=pdf_source, filetype="pdf")

    pages: List[str] = []
    for page in doc:
        pages.append(clean_text(page.get_text("text", sort=True)))
    return pages


def pdf_to_pages_pypdf(pdf_source: str | Path | bytes) -> List[str]:
    if isinstance(pdf_source, (str, Path)):
        reader = PdfReader(str(pdf_source))
    else:
        reader = PdfReader(BytesIO(pdf_source))

    pages: List[str] = []
    for page in reader.pages:
        pages.append(clean_text(page.extract_text() or ""))
    return pages


def pdf_to_pages(pdf_source: str | Path | bytes) -> List[str]:
    pages = pdf_to_pages_pymupdf(pdf_source)
    if any(len(p) > 50 for p in pages):
        return pages
    return pdf_to_pages_pypdf(pdf_source)


def pdf_to_text(pdf_source: str | Path | bytes) -> str:
    return "\f".join(pdf_to_pages(pdf_source))


def split_pages(text: str) -> List[str]:
    pages = [clean_text(p) for p in str(text).split("\f")]
    return [p for p in pages if p]


def search_first(
    text: str,
    patterns: Iterable[str],
    flags: int = re.IGNORECASE | re.MULTILINE | re.DOTALL,
) -> str:
    for pat in patterns:
        m = re.search(pat, text, flags)
        if m:
            return clean_text(m.group(1))
    return ""


def find_page(pages: List[str], needles: Iterable[str], excludes: Iterable[str] = ()) -> str:
    for page in pages:
        page_lower = page.lower()
        if all(n.lower() in page_lower for n in needles) and not any(e.lower() in page_lower for e in excludes):
            return page
    return ""


def parse_money(value: str) -> Decimal | None:
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


def money_to_str(value: Decimal | None) -> str:
    if value is None:
        return ""
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def extract_money(text: str, patterns: Iterable[str]) -> str:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if m:
            dec = parse_money(m.group(1))
            if dec is not None:
                return money_to_str(dec)
    return ""


def cleanup_name(raw: str) -> tuple[str, str]:
    raw = clean_text(raw)
    anrede = ""

    if re.match(r"(?i)^herr\b", raw):
        anrede = "Herr"
        raw = re.sub(r"(?i)^herr\b\.?\s*", "", raw).strip()
    elif re.match(r"(?i)^frau\b", raw):
        anrede = "Frau"
        raw = re.sub(r"(?i)^frau\b\.?\s*", "", raw).strip()

    return anrede, raw


def split_name(full_name: str) -> tuple[str, str, str]:
    full_name = clean_text(full_name)
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


def split_street_place(value: str) -> tuple[str, str]:
    value = clean_text(value)
    if not value:
        return "", ""

    if "," in value:
        street, place = value.split(",", 1)
        return street.strip(), place.strip(" -")
    return value, ""


def normalize_yes_no(value: str) -> str:
    v = clean_text(value).lower()
    if v in {"ja", "yes", "y", "true", "1"}:
        return "Ja"
    if v in {"nein", "no", "n", "false", "0"}:
        return "Nein"
    return clean_text(value)


def gender_fields(anrede: str) -> Dict[str, str]:
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


def extract_sonderkosten_from_pdf(pdf_source: str | Path | bytes) -> List[Dict[str, str]]:
    if fitz is None:
        return []

    if isinstance(pdf_source, (str, Path)):
        doc = fitz.open(str(pdf_source))
    else:
        doc = fitz.open(stream=pdf_source, filetype="pdf")

    for page in doc:
        page_text = clean_text(page.get_text("text", sort=True))
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
            sorted_rows.append((y, clean_text(line)))

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
                        name = clean_text(m.group(1))
                        betrag = money_to_str(parse_money(m.group(2)))
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

            name = clean_text(m.group(1))
            betrag = money_to_str(parse_money(m.group(2)))
            if name and betrag and name.lower() != "sonderkosten":
                items.append({"name": name, "betrag": betrag})

        return items

    return []
