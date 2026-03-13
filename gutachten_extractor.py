from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import fitz  # PyMuPDF


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
    # Regel: JA -> "" ; NEIN -> "nicht"
    v = (value or "").strip().lower()
    if v in {"ja", "yes", "true"}:
        return ""
    if v in {"nein", "no", "false"}:
        return "nicht"
    return value


def standard_defaults() -> Dict[str, str]:
    today = date.today().strftime("%d.%m.%Y")
    frist = (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y")
    return {"HEUTDATUM": today, "FIRST_DATUM": frist, "FRIST_DATUM": frist}


# -------------------------
# PDF -> Text
# -------------------------
def pdf_to_text(pdf_path: str | Path) -> str:
    pdf_path = str(pdf_path)
    doc = fitz.open(pdf_path)
    parts = []
    for i in range(doc.page_count):
        parts.append(doc.load_page(i).get_text("text"))
    return "\n".join(parts)


# -------------------------
# Pattern Engine
# -------------------------
@dataclass
class Pattern:
    regex: str
    flags: int = re.IGNORECASE | re.MULTILINE
    group: int = 1

    def find(self, text: str) -> str:
        m = re.search(self.regex, text, self.flags)
        if not m:
            return ""
        return (m.group(self.group) or "").strip()


# Gemeinsame Muster (GutachterExpress-Layout)
# -> Wenn etwas nicht gefunden wird, bleibt es "" (leer)
PATTERNS: Dict[str, Pattern] = {
    # Mandant
    "MANDANT_VORNAME": Pattern(r"Anspruchsteller\s*\n(?:Herr|Frau)\s+([A-Za-zÄÖÜäöüß\-]+)\s+([A-Za-zÄÖÜäöüß\-]+)", group=1),
    "MANDANT_NACHNAME": Pattern(r"Anspruchsteller\s*\n(?:Herr|Frau)\s+([A-Za-zÄÖÜäöüß\-]+)\s+([A-Za-zÄÖÜäöüß\-]+)", group=2),

    # Alternative: wenn die Zeile “Herrn <Vorname> <Nachname>” am Anfang steht
    "MANDANT_VORNAME_ALT": Pattern(r"\nHerrn\s*\n([A-Za-zÄÖÜäöüß\-]+)\s+([A-Za-zÄÖÜäöüß\-]+)\n", group=1),
    "MANDANT_NACHNAME_ALT": Pattern(r"\nHerrn\s*\n([A-Za-zÄÖÜäöüß\-]+)\s+([A-Za-zÄÖÜäöüß\-]+)\n", group=2),

    "MANDANT_STRASSE": Pattern(r"(?:Frau|Herrn|Herr)\s*\n[A-Za-zÄÖÜäöüß\- ]+\n([^\n]+)\n\d{5}", group=1),
    "MANDANT_PLZ_ORT": Pattern(r"(?:Frau|Herrn|Herr)\s*\n[A-Za-zÄÖÜäöüß\- ]+\n[^\n]+\n(\d{5}\s+[^\n]+)", group=1),

    # Unfall
    "UNFALL_DATUM": Pattern(r"Unfall\s+Datum\s+(\d{2}\.\d{2}\.\d{4})"),
    "UNFALL_ORT": Pattern(r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}.*?\n.*?\nOrt\s+([^\n]+)", group=1),
    # häufig steht Ort als "Unstrutstr. 2, 06122 Halle (Saale)"
    "UNFALL_STRASSE": Pattern(r"Unfall\s+Datum\s+\d{2}\.\d{2}\.\d{4}.*?\n.*?\nOrt\s+([^\n]+)", group=1),

    # Aktenzeichen + Fahrzeug
    "AKTENZEICHEN": Pattern(r"Aktenzeichen\s+([A-Z0-9\-\/]+)"),
    "KENNZEICHEN": Pattern(r"Amtliches\s+Kennzeichen\s+([A-ZÄÖÜ]{1,3}\s*[A-Z]{1,3}\s*\d{1,4})"),
    "FAHRZEUGTYP": Pattern(r"Modell/Haupttyp\s+([^\n]+)"),

    # Versicherung
    "VERSICHERUNG": Pattern(r"\nVersicherung\s+([^\n]+)"),
    "VER_STRASSE": Pattern(r"\nVersicherung\s+[^\n]+\nStraße\s+([^\n]+)"),
    "VER_ORT": Pattern(r"\nVersicherung\s+[^\n]+\nStraße\s+[^\n]+\nPLZ\s+Ort\s+([^\n]+)"),
    "SCHADENSNUMMER": Pattern(r"Versicherungs\-Nr\.\s*([A-Za-z0-9\/\-\_]+)"),

    # Vorsteuer
    "VORSTEUERBERECHTIGUNG": Pattern(r"Vorsteuerabzug\s+(Ja|Nein|unbekannt)"),
    # Reparatur / Kosten (Zusammenfassung)
    "REPARATURKOSTEN": Pattern(r"Reparaturkosten\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€"),
    "WERTMINDERUNG": Pattern(r"Merkantiler\s+Minderwert.*?\+\s*([\d\.\,]+)\s*€"),
    "SCHADENHOEHE_OHNE": Pattern(r"Schadenhöhe\s+ohne\s+MwSt\.\s+([\d\.\,]+)\s*€"),
    "WBW": Pattern(r"Wiederbeschaffungswert.*?\s+([\d\.\,]+)\s*€"),
    "RESTWERT": Pattern(r"Restwert\s+([\d\.\,]+)\s*€"),

    # Gutachterkosten: meistens aus Rechnung: "Gesamtbetrag inkl. MwSt."
    "GUTACHTERKOSTEN": Pattern(r"Gesamtbetrag\s+inkl\.\s+MwSt\.\s+([\d\.\,]+)\s*€"),
}


def extract_all(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}

    # Hauptmuster
    for key, pat in PATTERNS.items():
        if key.endswith("_ALT"):
            continue
        out[key] = pat.find(text)

    # Fallback für Mandant wenn “Anspruchsteller …” nicht greift
    if not out.get("MANDANT_VORNAME") or not out.get("MANDANT_NACHNAME"):
        out["MANDANT_VORNAME"] = PATTERNS["MANDANT_VORNAME_ALT"].find(text)
        out["MANDANT_NACHNAME"] = PATTERNS["MANDANT_NACHNAME_ALT"].find(text)

    # Vorsteuer normalisieren (Nein -> "nicht", Ja -> "")
    if out.get("VORSTEUERBERECHTIGUNG"):
        out["VORSTEUERBERECHTIGUNG"] = normalize_vorsteuer(out["VORSTEUERBERECHTIGUNG"])

    return out


def derive_fields(out: Dict[str, str]) -> Dict[str, str]:
    """
    Hier rechnen wir abgeleitete Felder, damit alle Schreiben funktionieren.
    z.B. Wiederbeschaffungswertaufwand = WBW - RESTWERT
    Kostensumme_X = Schadenhöhe ohne MwSt (oder Summe aus Feldern)
    """
    derived: Dict[str, str] = {}

    wbw = euro_to_float(out.get("WBW", ""))
    rw = euro_to_float(out.get("RESTWERT", ""))
    if wbw and (rw or rw == 0.0):
        wba = max(0.0, wbw - rw)
        derived["WIEDERBESCHAFFUNGSWERTAUFWAND"] = euro_format(wba)

    # Kostensumme_X: zuerst Schadenhöhe ohne MwSt, sonst Reparaturkosten + Wertminderung
    sh_ohne = euro_to_float(out.get("SCHADENHOEHE_OHNE", ""))
    if sh_ohne:
        derived["KOSTENSUMME_X"] = euro_format(sh_ohne)
    else:
        rep = euro_to_float(out.get("REPARATURKOSTEN", ""))
        wm = euro_to_float(out.get("WERTMINDERUNG", ""))
        if rep or wm:
            derived["KOSTENSUMME_X"] = euro_format(rep + wm)

    return derived


def build_context_for_template(template_keys: set[str], extracted: Dict[str, str]) -> Dict[str, Any]:
    # Start: alles leer
    ctx: Dict[str, Any] = {k: "" for k in template_keys}

    # Defaults: Datum / Frist nur setzen, wenn Key existiert
    defaults = standard_defaults()
    for k in template_keys:
        if k in defaults:
            ctx[k] = defaults[k]

    # Mapping: manche Templates heißen anders (MANDANT_STRASSE vs UNFALLE_STRASSE)
    alias = {
        "UNFALLE_STRASSE": "MANDANT_STRASSE",
        "MANDANT_STRASSE": "MANDANT_STRASSE",
    }

    # Werte setzen (nur wenn Key existiert)
    for k in template_keys:
        src = alias.get(k, k)
        if src in extracted and extracted[src]:
            ctx[k] = extracted[src]

    return ctx
