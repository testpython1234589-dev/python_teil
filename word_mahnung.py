"""
word_mahnung.py
===============
Erstellt ein Mahnungsschreiben (word_mahnung.docx) für jeden Gutachter-Typ
(GutachterExpress, Schnur, Stotko).

Platzhalter in word_mahnung.docx:
  {{SCHADENSNUMMER}}       – Schadennummer / VS-Nr.
  {{MANDANT_NACHNAME}}     – Nachname des Mandanten
  {{VERSICHERUNG}}         – Name der Versicherung
  {{UNFALL_DATUM}}         – Datum des Unfalls
  {{KENNZEICHEN_GEGNER}}   – Kennzeichen des Unfallgegners (AKZ)
  {{HEUTEDATUM}}           – heutiges Datum (Briefdatum)
  {{FRIST_DATUM}}          – ursprüngliche Frist aus dem Anspruchsschreiben
  {{KOSTENSUMME_X}}        – geforderter Gesamtbetrag
  {{NEUE_FRIST_DATUM}}     – neue letzte Frist (FRIST_DATUM + 7 Tage)
  {{MANDANT_VORNAME}}      – Vorname des Mandanten   (Adressblock)
  {{MANDANT_STRASSE}}      – Straße des Mandanten    (Adressblock)
  {{MANDANT_PLZ_ORT}}      – PLZ/Ort des Mandanten   (Adressblock)
  {{VER_STRASSE}}          – Straße der Versicherung
  {{VER_ORT}}              – PLZ/Ort der Versicherung

Verwendung:
    from word_mahnung import render_mahnung

    out_path = render_mahnung(extracted_data)
    print(f"Gespeichert: {out_path}")
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from docxtpl import DocxTemplate

# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_PATH = BASE_DIR / "word_mahnung.docx"

OUTPUT_DIR = BASE_DIR / "Output_wordvorlage"
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _safe_filename(value: str) -> str:
    """Gibt einen dateisystem-sicheren String zurück."""
    return "".join(c for c in (value or "").strip() if c.isalnum() or c in ("-", "_"))


def _calculate_neue_frist(frist_datum_str: str) -> str:
    """
    Neue letzte Frist für die Mahnung: FRIST_DATUM + 7 Tage.

    Erwartet Format DD.MM.YYYY.
    Fallback bei ungültigem Datum: heute + 21 Tage.
    """
    try:
        frist = datetime.strptime(frist_datum_str.strip(), "%d.%m.%Y")
        return (frist + timedelta(days=7)).strftime("%d.%m.%Y")
    except (ValueError, AttributeError):
        return (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y")


# ---------------------------------------------------------------------------
# Kontext aufbauen
# ---------------------------------------------------------------------------

def build_mahnung_context(extracted: Dict[str, Any]) -> Dict[str, str]:
    """
    Baut den Template-Kontext für das Mahnungsschreiben.

    Funktioniert mit allen Gutachter-Typen (GutachterExpress, Schnur, Stotko),
    da alle denselben derive_fields-Output aus gutachten_extractor.py nutzen.

    Args:
        extracted: Kombiniertes Dict aus extract_* + derive_fields
                   (z. B. aus gutachter_service.extract_from_pdf_bytes).

    Returns:
        Dict mit allen Platzhalter-Werten für word_mahnung.docx.
    """

    def _get(*keys: str, default: str = "") -> str:
        """Ersten nicht-leeren Wert aus den angegebenen Keys zurückgeben."""
        for key in keys:
            value = extracted.get(key)
            if value and str(value).strip():
                return str(value).strip()
        return default

    # --- Fristen ---
    # HEUTEDATUM       = Briefdatum (heute)
    # FRIST_DATUM      = ursprüngliche Frist aus Anspruchsschreiben (heute + 14 Tage,
    #                    berechnet in gutachten_extractor.derive_fields)
    # NEUE_FRIST_DATUM = letzte Frist in der Mahnung (FRIST_DATUM + 7 Tage)
    heute_str        = datetime.now().strftime("%d.%m.%Y")
    frist_datum      = _get("FRIST_DATUM", "FIRST_DATUM", default=heute_str)
    neue_frist_datum = _calculate_neue_frist(frist_datum)

    return {
        # --- Kopfzeile / Betreff ---
        "SCHADENSNUMMER":     _get("SCHADENSNUMMER", "SCHADENNUMMER"),
        "MANDANT_NACHNAME":   _get("MANDANT_NACHNAME"),
        "VERSICHERUNG":       _get("VERSICHERUNG", "VRSICHERUNG"),
        "UNFALL_DATUM":       _get("UNFALL_DATUM"),
        "KENNZEICHEN_GEGNER": _get("KENNZEICHEN_GEGNER", "KENNZEICHEN"),

        # --- Brieftext ---
        "HEUTEDATUM":         heute_str,
        "FRIST_DATUM":        frist_datum,
        "KOSTENSUMME_X":      _get("KOSTENSUMME_X", "KOSTENSUMME_TOTALSCHADEN", "KOSTENSUMME_REPARATUR"),
        "NEUE_FRIST_DATUM":   neue_frist_datum,

        # --- Adressblock Mandant ---
        "MANDANT_VORNAME":    _get("MANDANT_VORNAME"),
        "MANDANT_STRASSE":    _get("MANDANT_STRASSE"),
        "MANDANT_PLZ_ORT":    _get("MANDANT_PLZ_ORT"),

        # --- Adressblock Versicherung ---
        "VER_STRASSE":        _get("VER_STRASSE"),
        "VER_ORT":            _get("VER_ORT"),
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_mahnung(
    extracted: Dict[str, Any],
    template_path: Path | str | None = None,
    output_dir: Path | str | None = None,
) -> Path:
    """
    Rendert das Mahnungsschreiben und speichert es als .docx.

    Args:
        extracted:     Kombiniertes Ergebnis-Dict aus gutachter_service.
        template_path: Pfad zur Vorlage. Standard: word_mahnung.docx
                       im gleichen Verzeichnis wie dieses Modul.
        output_dir:    Ausgabepfad. Standard: Output_wordvorlage/

    Returns:
        Path zum gespeicherten Dokument.

    Raises:
        FileNotFoundError: Wenn die Vorlage nicht gefunden wird.
    """
    tpl_path = Path(template_path) if template_path else TEMPLATE_PATH
    out_dir  = Path(output_dir)    if output_dir  else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if not tpl_path.exists():
        raise FileNotFoundError(
            f"Vorlage nicht gefunden: {tpl_path}\n"
            f"Bitte 'word_mahnung.docx' im Verzeichnis '{tpl_path.parent}' ablegen."
        )

    context = build_mahnung_context(extracted)

    # Dateiname: Mahnung_<Nachname>_<TT-MM-JJJJ>.docx
    nachname_safe = _safe_filename(context.get("MANDANT_NACHNAME", "Unbekannt"))
    timestamp     = datetime.now().strftime("%d-%m-%Y")
    out_path      = out_dir / f"Mahnung_{nachname_safe}_{timestamp}.docx"

    tpl = DocxTemplate(str(tpl_path))
    tpl.render({k: (v or "") for k, v in context.items()})
    tpl.save(str(out_path))

    return out_path


# ---------------------------------------------------------------------------
# Standalone-Test  →  python word_mahnung.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_data: Dict[str, Any] = {
        "SCHADENSNUMMER":     "HUK-2026-123456",
        "MANDANT_VORNAME":    "Max",
        "MANDANT_NACHNAME":   "Mustermann",
        "MANDANT_STRASSE":    "Musterstraße 12",
        "MANDANT_PLZ_ORT":    "12345 Musterstadt",
        "UNFALL_DATUM":       "15.05.2026",
        "KENNZEICHEN_GEGNER": "HAL-AB-123",
        "FRIST_DATUM":        "15.06.2026",
        "KOSTENSUMME_X":      "3.850,00 €",
        "VERSICHERUNG":       "Allianz Versicherungs-AG",
        "VER_STRASSE":        "Königinstraße 28",
        "VER_ORT":            "80802 München",
    }

    ctx = build_mahnung_context(test_data)

    print("Kontext-Vorschau:")
    for key, val in ctx.items():
        print(f"  {{{{ {key:<25} }}}}  =  {val}")

    try:
        path = render_mahnung(test_data)
        print(f"\n✅ Mahnung gespeichert: {path}")
    except FileNotFoundError as e:
        print(f"\n⚠️  {e}")
