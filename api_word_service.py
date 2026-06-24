from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import sys
import uuid
import shutil

from api.config import GENERATED_DIR, BASE_DIR

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def find_template(template_file: str) -> Path:
    """
    Sucht eine Word-Vorlage im Repo.
    Für den Start einfach: Dateiname muss existieren.
    Später ersetzt du das durch Datenbank/Template-Konfiguration.
    """
    candidates = list(BASE_DIR.glob(f"**/{template_file}"))

    candidates = [
        p for p in candidates
        if p.is_file()
        and p.suffix.lower() == ".docx"
        and "generated" not in str(p).lower()
        and "~$" not in p.name
    ]

    if not candidates:
        raise FileNotFoundError(f"Word-Vorlage nicht gefunden: {template_file}")

    return candidates[0]


def generate_word_document(template_file: str, context: Dict[str, Any]) -> Path:
    """
    Zentrale API-Funktion für Werte → Word-Datei.

    Versucht zuerst dein bestehendes word_backend.py zu verwenden.
    Falls die Funktion anders heißt, musst du unten den Funktionsnamen anpassen.
    """
    template_path = find_template(template_file)
    output_filename = f"generated_{uuid.uuid4().hex}.docx"
    output_path = GENERATED_DIR / output_filename

    try:
        import word_backend as wb

        # HIER ggf. anpassen:
        # Mögliche Funktionsnamen in deinem Projekt.
        if hasattr(wb, "render_docx"):
            result = wb.render_docx(str(template_path), context, str(output_path))
        elif hasattr(wb, "generate_word"):
            result = wb.generate_word(str(template_path), context, str(output_path))
        elif hasattr(wb, "create_docx"):
            result = wb.create_docx(str(template_path), context, str(output_path))
        elif hasattr(wb, "fill_template"):
            result = wb.fill_template(str(template_path), context, str(output_path))
        else:
            # Fallback: direkte docxtpl-Nutzung
            from docxtpl import DocxTemplate

            doc = DocxTemplate(str(template_path))
            doc.render(context)
            doc.save(str(output_path))
            result = output_path

        # Falls dein bestehender Code selbst einen Pfad zurückgibt
        if result:
            result_path = Path(result)
            if result_path.exists() and result_path != output_path:
                shutil.copyfile(result_path, output_path)

    except Exception as exc:
        raise RuntimeError(f"Word-Generierung fehlgeschlagen: {exc}") from exc

    if not output_path.exists():
        raise FileNotFoundError("Word-Datei wurde nicht erzeugt.")

    return output_path
