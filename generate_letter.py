from __future__ import annotations

import argparse
from pathlib import Path

import word_backend as wb
import gutachten_service as gs


TEMPLATES = {
    "gutachterexpress": {
        "standard": ("vorlage_schreiben_gutachterexpress.docx", "Standard_schreiben_gutachterexpress"),
        "schreibentotalschaden": ("vorlage_schreibentotalschaden_gutachterexpress.docx", "schreibentotalschaden_gutachterexpress"),
    },
    "schnur": {
        "standard": ("vorlage_schreiben_schnur.docx", "Standard_schreiben_schnur"),
        "schreibentotalschaden": ("vorlage_schreibentotalschaden_schnur.docx", "schreibentotalschaden_schnur"),
    },
}


def main():
    ap = argparse.ArgumentParser(description="PDF Gutachten -> Word Schreiben")
    ap.add_argument("--pdf", required=True, help="Pfad zum Gutachten PDF")
    ap.add_argument("--gutachter", required=True, choices=TEMPLATES.keys(), help="Welcher Gutachter?")
    ap.add_argument("--tpl", required=True, help="Welche Vorlage / Schreiben?")
    ap.add_argument("--debug", action="store_true", help="Zeige gefundene Werte + fehlende Keys")
    args = ap.parse_args()

    gutachter_templates = TEMPLATES[args.gutachter]

    if args.tpl not in gutachter_templates:
        raise ValueError(
            f"Vorlage '{args.tpl}' nicht für Gutachter '{args.gutachter}' vorhanden. "
            f"Erlaubt: {', '.join(gutachter_templates.keys())}"
        )

    tpl_name, out_prefix = gutachter_templates[args.tpl]

    keys = wb.get_template_vars(tpl_name)

    pdf_bytes = Path(args.pdf).read_bytes()
    extracted = gs.extract_from_pdf_bytes(pdf_bytes, args.gutachter)
    ctx = gs.build_context(keys, extracted)

    if args.debug:
        missing = [k for k in sorted(keys) if not str(ctx.get(k, "")).strip()]
        print("=== Gutachter:", args.gutachter)
        print("=== Template:", tpl_name)
        print("=== Output Prefix:", out_prefix)
        print("=== Missing keys in context:", missing)
        print("=== Context Preview ===")
        for k in sorted(keys):
            print(f"{k}: {ctx.get(k,'')}")
        print("===")

    out_path = wb.render_word(tpl_name, ctx, out_prefix)
    print("Gespeichert:", out_path)


if __name__ == "__main__":
    main()
