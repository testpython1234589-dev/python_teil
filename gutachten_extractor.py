from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Dict, Any, List, Callable, Optional

import fitz  # PyMuPDF


# -------------------------
# Helpers
# -------------------------
def normalize_pdf_text(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\t", " ")
    t = re.sub(r"[ ]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


def join_lines(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s*\n\s*", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def euro_to_float(s: str) -> float:
    s = (s or "").strip()
    if not s:
        return 0.0
    s = s.replace("€", "").replace("EUR", "").strip()
    s = s.replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def euro_format(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalize_vorsteuer(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"ja", "yes", "y", "true"}:
        return ""
    if v in {"nein", "no", "n", "false"}:
        return "nicht"
    return value


def standard_defaults() -> Dict[str, str]:
    today = date.today().strftime("%d.%m.%Y")
    frist = (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y")
    return {"HEUTDATUM": today, "FIRST_DATUM": frist, "FRIST_DATUM": frist}


@dataclass
class MultiPattern:
    patterns: List[str]
    flags: int = re.IGNORECASE | re.MULTILINE | re.DOTALL
    group: int = 1
    postprocess: Optional[Callable[[str], str]] = None

    def find(self, text: str) -> str:
        for rx in self.patterns:
            m = re.search(rx, text, self.flags)
            if m:
                val = (m.group(self.group) or "").strip()
                if self.postprocess:
                    val = self.postprocess(val)
                return val
        return ""


def get_page_text(doc: fitz.Document, page_1_based: int) -> str:
    idx = page_1_based - 1
    if idx < 0 or idx >= doc.page_count:
        return ""
    return normalize_pdf_text(doc.load_page(idx).get_text("text"))


def find_beteiligte_page(doc: fitz.Document) -> int:
    """
    Sucht die Seite "Beteiligte, Besichtigungen & Auftrag" über Keywords.
    Gibt 1-based Seite zurück, sonst 0.
    """
    for i in range(doc.page_count):
        t = normalize_pdf_text(doc.load_page(i).get_text("text"))
        if re.search(r"Beteiligte", t, re.I) and re.search(r"Besichtig", t, re.I) and re.search(r"Auftrag", t, re.I):
            return i + 1
    return 0


# -------------------------
# Page-specific patterns
# -------------------------

# Unfall + Versicherung: Seite "Beteiligte, Besichtigungen & Auftrag"
P_BETEILIGTE = {
    "UNFALL_DATUM": MultiPattern([
        r"Unfall\s*Datum\s*(\d{2}\.\d{2}\.\d{4})",
        r"Unfalldatum\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
        r"Schadentag\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
    ]),
    "UNFALL_STRASSE": MultiPattern([
        r"(?:Unfallort|Unfallstelle|Ort)\s*[:\-]?\s*\n\s*([^\n]+)",
        r"(?:Unfallort|Unfallstelle|Ort)\s*[:\-]?\s*([^\n]+)",
    ], postprocess=join_lines),
    "UNFALL_ORT": MultiPattern([
        r"(?:Unfallort|Unfallstelle|Ort)\s*[:\-]?\s*\n\s*[^\n]+\n\s*(\d{5}\s+[^\n]+)",
        r"(?:Unfallort|Unfallstelle|Ort)\s*[:\-]?\s*.*?(\d{5}\s+[A-Za-zÄÖÜäöüß\-\(\) ]+)",
    ], postprocess=join_lines),

    "VERSICHERUNG": MultiPattern(
        patterns=[
            r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b\s*[:\-]?\s*\n([\s\S]{5,240}?)\n(?:Straße|PLZ|Ort|Schaden|Schadennummer|Versicherungs\-Nr|$)",
            r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b\s*[:\-]?\s*([^\n]+)",
        ],
        group=2,
        postprocess=join_lines
    ),
    "VER_STRASSE": MultiPattern([
        r"(?:Straße|Str\.)\s*[:\-]?\s*([^\n]+)",
        r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b[\s\S]{0,320}?\n[^\n]+\n([^\n]+)\n\d{5}\s+[^\n]+",
    ], group=1, postprocess=join_lines),
    "VER_ORT": MultiPattern([
        r"(?:PLZ\s*Ort|Ort)\s*[:\-]?\s*([^\n]+)",
        r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b[\s\S]{0,320}?\n[^\n]+\n[^\n]+\n(\d{5}\s+[^\n]+)",
    ], group=1, postprocess=join_lines),

    "SCHADENSNUMMER": MultiPattern([
        r"Schadennummer\s*[:\-]?\s*([A-Za-z0-9\/\-\_]+)",
        r"Versicherungs\-Nr\.\s*[:\-]?\s*([A-Za-z0-9\/\-\_]+)",
        r"Schaden\-Nr\.\s*[:\-]?\s*([A-Za-z0-9\/\-\_]+)",
    ]),
}

# Auto: Seite 2
P_AUTO = {
    "KENNZEICHEN": MultiPattern([
        r"Amtliches\s+Kennzeichen\s+([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,3}\s*\d{1,4})",
        r"Kennzeichen\s*[:\-]?\s*([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,3}\s*\d{1,4})",
    ]),
    "FAHRZEUGTYP": MultiPattern([
        r"Modell/Haupttyp\s+([^\n]+)",
        r"Fahrzeugtyp\s*[:\-]?\s*([^\n]+)",
    ], postprocess=join_lines),
    "AKTENZEICHEN": MultiPattern([
        r"Aktenzeichen\s+([A-Z0-9\-\/]+)",
        r"\bGA\-[A-Z0-9\-\/]+\b",
    ]),
    "VORSTEUERBERECHTIGUNG": MultiPattern([
        r"Vorsteuerabzug\s+(Ja|Nein|unbekannt)",
        r"Vorsteuerberechtigt\s*[:\-]?\s*(Ja|Nein)",
    ]),
}

# Gutachterkosten: Seite 1
P_GUTACHTER = {
    "GUTACHTERKOSTEN": MultiPattern([
        r"Gesamtbetrag\s+inkl\.\s+MwSt\.\s+([\d\.\,]+)\s*€",
        r"Rechnungsbetrag\s+([\d\.\,]+)\s*€",
    ]),
}

# Zusammenfassung / Rechnung: Seite 3
P_ZUSAMMENFASSUNG = {
    "REPARATURKOSTEN": MultiPattern([
        r"Reparaturkosten\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€",
        r"Reparaturkosten\s+netto\s+([\d\.\,]+)\s*€",
    ]),
    "WERTMINDERUNG": MultiPattern([
        r"Merkantiler\s+Minderwert.*?([\d\.\,]+)\s*€",
        r"Wertminderung\s+([\d\.\,]+)\s*€",
    ]),
    "KOSTENPAUSCHALE": MultiPattern([
        r"Kostenpauschale\s+([\d\.\,]+)\s*€",
    ]),
    "SCHADENHOEHE_OHNE": MultiPattern([
        r"Schadenhöhe\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€",
        r"Schadenhöhe\s+netto\s+([\d\.\,]+)\s*€",
    ]),
}

# Schadenhergang: Seite 10
P_SCHADENHERGANG = {
    "SCHADENHERGANG": MultiPattern([
        r"Schadenhergang\s*\n([\s\S]{30,1500}?)(?:\n\s*[A-ZÄÖÜ][^\n]{2,70}\n|$)",
    ], postprocess=join_lines),
}


def apply_patterns(text: str, patterns: Dict[str, MultiPattern], out: Dict[str, str]) -> None:
    for k, mp in patterns.items():
        val = mp.find(text)
        if val:
            out[k] = val


def derive_fields(out: Dict[str, str]) -> Dict[str, str]:
    derived: Dict[str, str] = {}

    sh = euro_to_float(out.get("SCHADENHOEHE_OHNE", ""))
    if sh:
        derived["KOSTENSUMME_X"] = euro_format(sh)
    else:
        rep = euro_to_float(out.get("REPARATURKOSTEN", ""))
        wm = euro_to_float(out.get("WERTMINDERUNG", ""))
        kp = euro_to_float(out.get("KOSTENPAUSCHALE", ""))
        gut = euro_to_float(out.get("GUTACHTERKOSTEN", ""))
        s = rep + wm + kp + gut
        if s:
            derived["KOSTENSUMME_X"] = euro_format(s)

    if "VORSTEUERBERECHTIGUNG" in out:
        out["VORSTEUERBERECHTIGUNG"] = normalize_vorsteuer(out.get("VORSTEUERBERECHTIGUNG", ""))

    return derived


def extract_from_pdf_bytes(pdf_bytes: bytes) -> Dict[str, str]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out: Dict[str, str] = {}

    beteiligte_page = find_beteiligte_page(doc)
    if beteiligte_page:
        apply_patterns(get_page_text(doc, beteiligte_page), P_BETEILIGTE, out)

    apply_patterns(get_page_text(doc, 2), P_AUTO, out)
    apply_patterns(get_page_text(doc, 1), P_GUTACHTER, out)
    apply_patterns(get_page_text(doc, 3), P_ZUSAMMENFASSUNG, out)
    apply_patterns(get_page_text(doc, 10), P_SCHADENHERGANG, out)

    out.update({k: v for k, v in standard_defaults().items() if k not in out or not str(out[k]).strip()})
    out.update(derive_fields(out))

    return out


def build_context_for_template(template_keys: set[str], extracted: Dict[str, str]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {k: "" for k in template_keys}

    alias = {
        "UNFALLE_STRASSE": "MANDANT_STRASSE",
        "MANDANT_STRASSE": "MANDANT_STRASSE",
    }

    for k in template_keys:
        src = alias.get(k, k)
        if src in extracted and str(extracted[src]).strip():
            ctx[k] = extracted[src]

    defaults = standard_defaults()
    for k in template_keys:
        if k in defaults and not str(ctx.get(k, "")).strip():
            ctx[k] = defaults[k]

    return ctx
