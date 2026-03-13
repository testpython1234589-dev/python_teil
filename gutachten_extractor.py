from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Dict, Any, List, Set, Callable, Optional


# -------------------------
# Text-Normalisierung
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


# -------------------------
# Geld/Format + Regeln
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


# -------------------------
# BLOCK-Extraktion
# -------------------------
def extract_block(text: str, start_rx: str, end_rx_list: list[str], max_len: int = 2200) -> str:
    m = re.search(start_rx, text, re.IGNORECASE | re.MULTILINE)
    if not m:
        return ""
    start = m.end()
    sub = text[start:start + max_len]

    ends = []
    for erx in end_rx_list:
        em = re.search(erx, sub, re.IGNORECASE | re.MULTILINE)
        if em:
            ends.append(em.start())
    if ends:
        sub = sub[:min(ends)]
    return sub.strip()


def get_mandant_block(text: str) -> str:
    return extract_block(
        text,
        start_rx=r"\b(Anspruchsteller|Geschädigte?r)\b",
        end_rx_list=[r"\b(Beteiligte|Besichtigung|Auftrag)\b", r"\bVersicherung\b", r"\bFahrzeug\b", r"\bUnfall\b", r"\bAktenzeichen\b"],
        max_len=2500
    ) or extract_block(
        text,
        start_rx=r"\b(Frau|Herrn|Herr)\b",
        end_rx_list=[r"\b(Beteiligte|Besichtigung|Auftrag)\b", r"\bVersicherung\b", r"\bFahrzeug\b", r"\bUnfall\b", r"\bAktenzeichen\b"],
        max_len=2500
    )


def get_beteiligte_block(text: str) -> str:
    # Ziel: Abschnitt "Beteiligte, Besichtigung und Auftrag"
    return extract_block(
        text,
        start_rx=r"\b(Beteiligte|Besichtigung|Auftrag)\b",
        end_rx_list=[r"\bFahrzeug\b", r"\bReparatur\b", r"\bSchadenhergang\b", r"\bKalkulation\b", r"\bZusammenfassung\b", r"\bErgebnis\b"],
        max_len=4500
    )


def get_versicherung_block(text: str) -> str:
    return extract_block(
        text,
        start_rx=r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b",
        end_rx_list=[r"\bFahrzeug\b", r"\bUnfall\b", r"\bSchadenhergang\b", r"\bAktenzeichen\b"],
        max_len=2500
    )


# -------------------------
# Pattern Engine (Fallbacks)
# -------------------------
@dataclass
class MultiPattern:
    patterns: List[str]
    flags: int = re.IGNORECASE | re.MULTILINE
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


# -------------------------
# Mandant: nur im Mandantenblock zuverlässig
# -------------------------
MANDANT_PATTERNS: Dict[str, MultiPattern] = {
    "MANDANT_VORNAME": MultiPattern([
        r"(?:Herr|Frau)\s+([A-Za-zÄÖÜäöüß\-]+)\s+[A-Za-zÄÖÜäöüß\-]+",
        r"Herrn\s*\n([A-Za-zÄÖÜäöüß\-]+)\s+[A-Za-zÄÖÜäöüß\-]+",
    ]),
    "MANDANT_NACHNAME": MultiPattern([
        r"(?:Herr|Frau)\s+[A-Za-zÄÖÜäöüß\-]+\s+([A-Za-zÄÖÜäöüß\-]+)",
        r"Herrn\s*\n[A-Za-zÄÖÜäöüß\-]+\s+([A-Za-zÄÖÜäöüß\-]+)",
    ]),
    "MANDANT_STRASSE": MultiPattern([
        r"(?:Herr|Frau|Herrn)\s+[^\n]+\n([^\n]+)\n\d{5}\s+[^\n]+",
        r"\n([^\n]+)\n\d{5}\s+[^\n]+",
    ], postprocess=join_lines),
    "MANDANT_PLZ_ORT": MultiPattern([
        r"(?:Herr|Frau|Herrn)\s+[^\n]+\n[^\n]+\n(\d{5}\s+[^\n]+)",
        r"\n[^\n]+\n(\d{5}\s+[^\n]+)",
    ], postprocess=join_lines),
}


# -------------------------
# Beteiligte/Besichtigung/Auftrag: Unfall + Versicherung sind HIER "source of truth"
# -------------------------
BETEILIGTE_PATTERNS: Dict[str, MultiPattern] = {
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

    # Versicherung: mehrzeilig
    "VERSICHERUNG": MultiPattern(
        patterns=[
            r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b\s*[:\-]?\s*\n([\s\S]{5,240}?)\n(?:Straße|PLZ|Ort|Schaden|Schadennummer|Versicherungs\-Nr|$)",
            r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b\s*[:\-]?\s*([^\n]+)",
        ],
        group=2,
        postprocess=join_lines
    ),

    # Versicherungsstraße/Ort: bevorzugt Label-Form, sonst Block-Form
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


# -------------------------
# Global patterns (nur wenn Beteiligte-Block nichts liefert)
# -------------------------
GLOBAL_PATTERNS: Dict[str, MultiPattern] = {
    "AKTENZEICHEN": MultiPattern([r"Aktenzeichen\s+([A-Z0-9\-\/]+)", r"\bGA\-[A-Z0-9\-\/]+\b"]),
    "KENNZEICHEN": MultiPattern([
        r"Amtliches\s+Kennzeichen\s+([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,3}\s*\d{1,4})",
        r"Kennzeichen\s*[:\-]?\s*([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,3}\s*\d{1,4})",
    ]),
    "FAHRZEUGTYP": MultiPattern([r"Modell/Haupttyp\s+([^\n]+)", r"Fahrzeugtyp\s*[:\-]?\s*([^\n]+)"], postprocess=join_lines),

    "SCHADENHERGANG": MultiPattern([
        r"(?:Schadenhergang|Unfallhergang)\s*\n([\s\S]{20,900}?)\n(?:\s*[A-ZÄÖÜ][^\n]{2,60}\s*\n|$)",
        r"(?:Angaben\s+des\s+Fahrzeughalters|Angaben\s+des\s+Geschädigten)\s*\n([\s\S]{20,900}?)\n(?:\s*[A-ZÄÖÜ][^\n]{2,60}\s*\n|$)",
        r"(Nach\s+Angaben[\s\S]{30,450}?)(?:\n\n|$)",
    ], postprocess=join_lines),

    "VORSTEUERBERECHTIGUNG": MultiPattern([r"Vorsteuerabzug\s+(Ja|Nein|unbekannt)", r"Vorsteuerberechtigt\s*[:\-]?\s*(Ja|Nein)"]),
    "REPARATURKOSTEN": MultiPattern([r"Reparaturkosten\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€", r"Reparaturkosten\s+netto\s+([\d\.\,]+)\s*€"]),
    "WERTMINDERUNG": MultiPattern([r"Merkantiler\s+Minderwert.*?([\d\.\,]+)\s*€", r"Wertminderung\s+([\d\.\,]+)\s*€"]),
    "SCHADENHOEHE_OHNE": MultiPattern([r"Schadenhöhe\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€", r"Schadenhöhe\s+netto\s+([\d\.\,]+)\s*€"]),
    "WBW": MultiPattern([r"Wiederbeschaffungswert.*?\s+([\d\.\,]+)\s*€", r"Wiederbeschaffungswert\s+([\d\.\,]+)\s*€"]),
    "RESTWERT": MultiPattern([r"Restwert\s+([\d\.\,]+)\s*€", r"Restwert.*?\s+([\d\.\,]+)\s*€"]),
}


# Versicherung-Block-Fallback (wenn Beteiligte-Block fehlt)
VERS_FALLBACK_PATTERNS: Dict[str, MultiPattern] = {
    "VERSICHERUNG": MultiPattern(
        patterns=[
            r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b\s*[:\-]?\s*\n([\s\S]{5,240}?)\n(?:Straße|PLZ|Ort|Schaden|Schadennummer|Versicherungs\-Nr|$)",
        ],
        group=2,
        postprocess=join_lines
    ),
    "VER_STRASSE": MultiPattern([
        r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b[\s\S]{0,320}?\n[^\n]+\n([^\n]+)\n\d{5}\s+[^\n]+",
    ], group=2, postprocess=join_lines),
    "VER_ORT": MultiPattern([
        r"\b(Versicherung|Haftpflichtversicherung|Versicherer)\b[\s\S]{0,320}?\n[^\n]+\n[^\n]+\n(\d{5}\s+[^\n]+)",
    ], group=2, postprocess=join_lines),
}


def extract_all(text: str) -> Dict[str, str]:
    text = normalize_pdf_text(text)
    out: Dict[str, str] = {}

    mandant_block = get_mandant_block(text)
    beteiligte_block = get_beteiligte_block(text)
    vers_block = get_versicherung_block(text)

    # 1) Mandant (nur Mandant-Block)
    for k, mp in MANDANT_PATTERNS.items():
        out[k] = mp.find(mandant_block) or mp.find(text)

    # 2) Beteiligte-Block = Source of truth für Unfall/Versicherung
    for k, mp in BETEILIGTE_PATTERNS.items():
        out[k] = mp.find(beteiligte_block)

    # 3) Globale Felder (Aktenzeichen, Kennzeichen, Fahrzeugtyp, Kosten etc.)
    for k, mp in GLOBAL_PATTERNS.items():
        out[k] = out.get(k, "") or mp.find(text)

    # 4) Falls Beteiligte-Block Versicherung nicht liefert: Versicherungs-Block-Fallback
    for k, mp in VERS_FALLBACK_PATTERNS.items():
        if not str(out.get(k, "")).strip():
            out[k] = mp.find(vers_block) or mp.find(text)

    # 5) Vorsteuer normalisieren
    if out.get("VORSTEUERBERECHTIGUNG"):
        out["VORSTEUERBERECHTIGUNG"] = normalize_vorsteuer(out["VORSTEUERBERECHTIGUNG"])

    return out


def derive_fields(out: Dict[str, str]) -> Dict[str, str]:
    derived: Dict[str, str] = {}

    wbw = euro_to_float(out.get("WBW", ""))
    rw = euro_to_float(out.get("RESTWERT", ""))
    if wbw and (rw or rw == 0.0):
        derived["WIEDERBESCHAFFUNGSWERTAUFWAND"] = euro_format(max(0.0, wbw - rw))

    sh_ohne = euro_to_float(out.get("SCHADENHOEHE_OHNE", ""))
    if sh_ohne:
        derived["KOSTENSUMME_X"] = euro_format(sh_ohne)
    else:
        rep = euro_to_float(out.get("REPARATURKOSTEN", ""))
        wm = euro_to_float(out.get("WERTMINDERUNG", ""))
        if rep or wm:
            derived["KOSTENSUMME_X"] = euro_format(rep + wm)

    return derived


def build_context_for_template(template_keys: Set[str], merged: Dict[str, str]) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {k: "" for k in template_keys}

    defaults = standard_defaults()
    for k in template_keys:
        if k in defaults:
            ctx[k] = defaults[k]

    alias = {
        "UNFALLE_STRASSE": "MANDANT_STRASSE",
        "MANDANT_STRASSE": "MANDANT_STRASSE",
        "KOSTENSUMME_X": "KOSTENSUMME_X",
    }

    for k in template_keys:
        src = alias.get(k, k)
        if src in merged and str(merged[src]).strip():
            ctx[k] = merged[src]

    return ctx
