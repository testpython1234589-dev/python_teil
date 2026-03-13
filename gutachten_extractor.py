from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Dict, Any, List, Set


# -------------------------
# Geld / Format Helpers
# -------------------------
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


def normalize_pdf_text(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\t", " ")
    t = re.sub(r"[ ]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t


# -------------------------
# Pattern Engine (Fallbacks)
# -------------------------
@dataclass
class MultiPattern:
    patterns: List[str]
    flags: int = re.IGNORECASE | re.MULTILINE
    group: int = 1

    def find(self, text: str) -> str:
        for rx in self.patterns:
            m = re.search(rx, text, self.flags)
            if m:
                return (m.group(self.group) or "").strip()
        return ""


PATTERNS: Dict[str, MultiPattern] = {
    # Mandant
    "MANDANT_VORNAME": MultiPattern([
        r"Anspruchsteller\s*\n(?:Herr|Frau)\s+([A-Za-zÄÖÜäöüß\-]+)\s+[A-Za-zÄÖÜäöüß\-]+",
        r"\n(?:Herr|Frau)\s+([A-Za-zÄÖÜäöüß\-]+)\s+[A-Za-zÄÖÜäöüß\-]+\n",
        r"\nHerrn\s*\n([A-Za-zÄÖÜäöüß\-]+)\s+[A-Za-zÄÖÜäöüß\-]+\n",
    ]),
    "MANDANT_NACHNAME": MultiPattern([
        r"Anspruchsteller\s*\n(?:Herr|Frau)\s+[A-Za-zÄÖÜäöüß\-]+\s+([A-Za-zÄÖÜäöüß\-]+)",
        r"\n(?:Herr|Frau)\s+[A-Za-zÄÖÜäöüß\-]+\s+([A-Za-zÄÖÜäöüß\-]+)\n",
        r"\nHerrn\s*\n[A-Za-zÄÖÜäöüß\-]+\s+([A-Za-zÄÖÜäöüß\-]+)\n",
    ]),
    "MANDANT_STRASSE": MultiPattern([
        r"(?:Frau|Herrn|Herr)\s*\n[^\n]+\n([^\n]+)\n\d{5}\s+[^\n]+",
        r"Adresse\s*\n([^\n]+)\n\d{5}\s+[^\n]+",
    ]),
    "MANDANT_PLZ_ORT": MultiPattern([
        r"(?:Frau|Herrn|Herr)\s*\n[^\n]+\n[^\n]+\n(\d{5}\s+[^\n]+)",
        r"Adresse\s*\n[^\n]+\n(\d{5}\s+[^\n]+)",
    ]),

    # Unfall
    "UNFALL_DATUM": MultiPattern([
        r"Unfall\s*Datum\s*(\d{2}\.\d{2}\.\d{4})",
        r"Unfalldatum\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
        r"Schadentag\s*[:\-]?\s*(\d{2}\.\d{2}\.\d{4})",
    ]),
    "UNFALL_STRASSE": MultiPattern([
        r"(?:Unfallort|Unfallstelle|Ort)\s*\n\s*([^\n,]+(?:\s+\d+[a-zA-Z]?)?)",
        r"(?:Unfallort|Unfallstelle|Ort)\s*[:\-]?\s*([^\n,]+(?:\s+\d+[a-zA-Z]?)?)",
        r"(?:Unfallort|Unfallstelle|Ort)\s*\n\s*([^\n]+,\s*\d{5}\s+[^\n]+)",
    ]),
    "UNFALL_ORT": MultiPattern([
        r"(?:Unfallort|Unfallstelle|Ort)\s*\n(?:[^\n]+\n)?\s*(\d{5}\s+[^\n]+)",
        r"(?:Unfallort|Unfallstelle|Ort)\s*[:\-]?\s*(\d{5}\s+[^\n]+)",
        r"(?:Unfallort|Unfallstelle|Ort)\s*\n(?:[^\n]+,\s*)?([A-Za-zÄÖÜäöüß\-\(\) ]{3,})",
    ]),

    # Aktenzeichen / Fahrzeug
    "AKTENZEICHEN": MultiPattern([
        r"Aktenzeichen\s+([A-Z0-9\-\/]+)",
        r"GA\-[A-Z0-9\-\/]+",  # fallback, wenn nur im Text vorkommt
    ]),
    "KENNZEICHEN": MultiPattern([
        r"Amtliches\s+Kennzeichen\s+([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,3}\s*\d{1,4})",
        r"Kennzeichen\s*[:\-]?\s*([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,3}\s*\d{1,4})",
    ]),
    "FAHRZEUGTYP": MultiPattern([
        r"Modell/Haupttyp\s+([^\n]+)",
        r"Fahrzeugtyp\s*[:\-]?\s*([^\n]+)",
    ]),

    # Versicherung
    "VERSICHERUNG": MultiPattern([
        r"\bVersicherung\b\s*\n([^\n]+)",
        r"\bHaftpflichtversicherung\b\s*\n([^\n]+)",
        r"\bVersicherer\b\s*[:\-]?\s*([^\n]+)",
    ]),
    "VER_STRASSE": MultiPattern([
        r"\bVersicherung\b\s*\n[^\n]+\n([^\n]+)\n\d{5}\s+[^\n]+",
        r"\bHaftpflichtversicherung\b\s*\n[^\n]+\n([^\n]+)\n\d{5}\s+[^\n]+",
        r"Straße\s+([^\n]+)\nPLZ\s*Ort",
    ]),
    "VER_ORT": MultiPattern([
        r"\bVersicherung\b\s*\n[^\n]+\n[^\n]+\n(\d{5}\s+[^\n]+)",
        r"\bHaftpflichtversicherung\b\s*\n[^\n]+\n[^\n]+\n(\d{5}\s+[^\n]+)",
        r"PLZ\s*Ort\s+([^\n]+)",
    ]),
    "SCHADENSNUMMER": MultiPattern([
        r"Schadennummer\s*[:\-]?\s*([A-Za-z0-9\/\-\_]+)",
        r"Schaden\-Nr\.\s*[:\-]?\s*([A-Za-z0-9\/\-\_]+)",
        r"Versicherungs\-Nr\.\s*([A-Za-z0-9\/\-\_]+)",
    ]),

    # Schadenhergang (Abschnitt)
    "SCHADENHERGANG": MultiPattern([
        r"(?:Schadenhergang|Unfallhergang)\s*\n([\s\S]{20,900}?)\n(?:\s*[A-ZÄÖÜ][^\n]{2,60}\s*\n|$)",
        r"(?:Angaben\s+des\s+Fahrzeughalters|Angaben\s+des\s+Geschädigten)\s*\n([\s\S]{20,900}?)\n(?:\s*[A-ZÄÖÜ][^\n]{2,60}\s*\n|$)",
        r"(Nach\s+Angaben[\s\S]{30,400}?)(?:\n\n|$)",
    ]),

    # Vorsteuer + Kosten
    "VORSTEUERBERECHTIGUNG": MultiPattern([
        r"Vorsteuerabzug\s+(Ja|Nein|unbekannt)",
        r"Vorsteuerberechtigt\s*[:\-]?\s*(Ja|Nein)",
    ]),
    "REPARATURKOSTEN": MultiPattern([
        r"Reparaturkosten\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€",
        r"Reparaturkosten\s+netto\s+([\d\.\,]+)\s*€",
    ]),
    "WERTMINDERUNG": MultiPattern([
        r"Merkantiler\s+Minderwert.*?([\d\.\,]+)\s*€",
        r"Wertminderung\s+([\d\.\,]+)\s*€",
    ]),
    "SCHADENHOEHE_OHNE": MultiPattern([
        r"Schadenhöhe\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€",
        r"Schadenhöhe\s+netto\s+([\d\.\,]+)\s*€",
    ]),
    "WBW": MultiPattern([
        r"Wiederbeschaffungswert.*?\s+([\d\.\,]+)\s*€",
        r"Wiederbeschaffungswert\s+([\d\.\,]+)\s*€",
    ]),
    "RESTWERT": MultiPattern([
        r"Restwert\s+([\d\.\,]+)\s*€",
        r"Restwert.*?\s+([\d\.\,]+)\s*€",
    ]),
}


def extract_all(text: str) -> Dict[str, str]:
    text = normalize_pdf_text(text)
    out: Dict[str, str] = {}
    for key, mp in PATTERNS.items():
        out[key] = mp.find(text)

    if out.get("VORSTEUERBERECHTIGUNG"):
        out["VORSTEUERBERECHTIGUNG"] = normalize_vorsteuer(out["VORSTEUERBERECHTIGUNG"])

    return out


def derive_fields(out: Dict[str, str]) -> Dict[str, str]:
    derived: Dict[str, str] = {}

    wbw = euro_to_float(out.get("WBW", ""))
    rw = euro_to_float(out.get("RESTWERT", ""))
    if wbw and (rw or rw == 0.0):
        derived["WIEDERBESCHAFFUNGSWERTAUFWAND"] = euro_format(max(0.0, wbw - rw))

    # Kostensumme: bevorzugt Schadenhöhe ohne MwSt
    sh_ohne = euro_to_float(out.get("SCHADENHOEHE_OHNE", ""))
    if sh_ohne:
        derived["KOSTENSUMME_X"] = euro_format(sh_ohne)
    else:
        rep = euro_to_float(out.get("REPARATURKOSTEN", ""))
        wm = euro_to_float(out.get("WERTMINDERUNG", ""))
        if rep or wm:
            derived["KOSTENSUMME_X"] = euro_format(rep + wm)

    return derived


def build_context_for_template(template_keys: Set[str], extracted: Dict[str, str]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {k: "" for k in template_keys}

    defaults = standard_defaults()
    for k in template_keys:
        if k in defaults:
            ctx[k] = defaults[k]

    # Alias Mapping (falls Templates unterschiedliche Key-Namen nutzen)
    alias = {
        "UNFALLE_STRASSE": "MANDANT_STRASSE",
        "MANDANT_STRASSE": "MANDANT_STRASSE",
        "KOSTENSUMME_X": "KOSTENSUMME_X",
    }

    for k in template_keys:
        src = alias.get(k, k)
        if src in extracted and extracted[src]:
            ctx[k] = extracted[src]

    return ctx
