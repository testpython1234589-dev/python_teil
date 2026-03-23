from __future__ import annotations

from pathlib import Path
from typing import Set, Dict, Any
from datetime import datetime
from docxtpl import DocxTemplate

BASE_DIR = Path(__file__).resolve().parent
VORLAGEN_DIR = BASE_DIR

OUTPUT_DIR = BASE_DIR / "Output_wordvorlage"
OUTPUT_DIR.mkdir(exist_ok=True)


def safe_filename(s: str) -> str:
    return "".join(c for c in (s or "").strip() if c.isalnum() or c in ("-", "_"))


def get_template_vars(tpl_name: str) -> Set[str]:
    tpl_path = VORLAGEN_DIR / tpl_name
    if not tpl_path.exists():
        raise FileNotFoundError(
            f"Vorlage nicht gefunden: {tpl_path}\n"
            f"Vorhandene .docx im Repo: {[p.name for p in VORLAGEN_DIR.glob('*.docx')]}"
        )
    tpl = DocxTemplate(str(tpl_path))
    return set(tpl.get_undeclared_template_variables() or [])


def render_word(tpl_name: str, context: Dict[str, Any], out_prefix: str) -> Path:
    tpl_path = VORLAGEN_DIR / tpl_name
    if not tpl_path.exists():
        raise FileNotFoundError(
            f"Vorlage nicht gefunden: {tpl_path}\n"
            f"Vorhandene .docx im Repo: {[p.name for p in VORLAGEN_DIR.glob('*.docx')]}"
        )

    tpl = DocxTemplate(str(tpl_path))
    clean_context = {k: ("" if v is None else v) for k, v in context.items()}
    tpl.render(clean_context)

    nachname = safe_filename(str(clean_context.get("MANDANT_NACHNAME", "Unbekannt") or "Unbekannt"))
    out_name = f"{out_prefix}_{nachname}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx"
    out_path = OUTPUT_DIR / out_name
    tpl.save(str(out_path))
    return out_path
