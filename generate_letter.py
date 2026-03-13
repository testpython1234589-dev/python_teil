from __future__ import annotations

import argparse
from pathlib import Path

import word_backend as wb
import gutachten_extractor as gx


TEMPLATES = {
    # Name in CLI -> (template_docx, out_prefix)
    "standard": ("vorlage_schreiben-1.docx", "Standard_schreiben"),
    "130": ("vorlage_130_prozent-1.docx", "130_prozent"),
    "ts_konkret": ("vorlage_totalschaden_konkret-1.docx", "totalschaden_konkret"),
    "konkret_unter_wbw": ("vorlage_konkret_unter_wbw-1.docx", "konkret_unter_wbw"),
    "ts_fiktiv": ("vorlage_totalschaden_fiktiv-1.docx", "totalschaden_fiktiv"),
    "schreibentotalschaden": ("vorlage_schreibentotalschaden-1.docx", "schreibentotalschaden"),
}


def main():
    ap = argparse.ArgumentParser(description="PDF Gutachten -> Word Schreiben (ohne KI, Regex-basiert)")
    ap.add_argument("--pdf", required=True, help="Pfad zum Gutachten PDF")
    ap.add_argument("--tpl", required=True, choices=TEMPLATES.keys(), help="Welche Vorlage / Schreiben?")
    ap.add_argument("--debug", action="store_true", help="Zeige gefundene Werte + fehlende Keys")
    args = ap.parse_args()

    tpl_name, out_prefix = TEMPLATES[args.tpl]

    # 1) Template-Keys
    keys = wb.get_template_vars(tpl_name)

    # 2) PDF -> Text
    text = gx.pdf_to_text(args.pdf)

    # 3) Extract
    extracted = gx.extract_all(text)
    derived = gx.derive_fields(extracted)

    # Merge extracted + derived (derived gewinnt)
    merged = {**extracted, **derived}

    # 4) Build context nur für Template-Keys
    ctx = gx.build_context_for_template(keys, merged)

    # 5) Debug: fehlende Keys
    if args.debug:
        missing = [k for k in sorted(keys) if not str(ctx.get(k, "")).strip()]
        print("=== Template:", tpl_name)
        print("=== Output Prefix:", out_prefix)
        print("=== Missing keys in context:", missing)
        print("=== Context Preview ===")
        for k in sorted(keys):
            print(f"{k}: {ctx.get(k,'')}")
        print("===")

    # 6) Render
    out_path = wb.render_word(tpl_name, ctx, out_prefix)
    print("Gespeichert:", out_path)


if __name__ == "__main__":
    main()
