from __future__ import annotations

import streamlit as st
from pathlib import Path

import word_backend as wb
import gutachten_extractor as gx


# -----------------------------
# Vorlagen / Schreiben
# -----------------------------
TEMPLATES = {
    "Standard Schreiben": ("vorlage_schreiben-1.docx", "Standard_schreiben"),
    "130 Prozent": ("vorlage_130_prozent-1.docx", "130_prozent"),
    "Totalschaden (konkret)": ("vorlage_totalschaden_konkret-1.docx", "totalschaden_konkret"),
    "Konkret unter WBW": ("vorlage_konkret_unter_wbw-1.docx", "konkret_unter_wbw"),
    "Totalschaden (fiktiv)": ("vorlage_totalschaden_fiktiv-1.docx", "totalschaden_fiktiv"),
    "Schreiben Totalschaden": ("vorlage_schreibentotalschaden-1.docx", "schreibentotalschaden"),
}


st.set_page_config(page_title="Gutachten → Schreiben (ohne KI)", layout="wide")
st.title("Gutachten → Word-Schreiben (ohne KI, Regex-basiert)")

with st.expander("📁 Vorlagen im Repo anzeigen", expanded=False):
    st.write(str(wb.VORLAGEN_DIR))
    st.write([p.name for p in wb.VORLAGEN_DIR.glob("*.docx")])


# -----------------------------
# UI: Auswahl + Upload
# -----------------------------
template_label = st.selectbox("Vorlage wählen", list(TEMPLATES.keys()))
tpl_name, out_prefix = TEMPLATES[template_label]

pdf_file = st.file_uploader("Gutachten als PDF hochladen", type=["pdf"])

col1, col2 = st.columns(2)
with col1:
    show_debug = st.toggle("Debug anzeigen (Werte + fehlende Keys)", value=True)
with col2:
    strict_mode = st.toggle("Strict: Abbrechen wenn wichtige Keys fehlen", value=False)

st.caption("Hinweis: Das funktioniert nur zuverlässig bei Text-PDFs (nicht reine Scans ohne OCR).")

# Optional: wichtige Keys je Schreiben (kannst du erweitern)
REQUIRED_KEYS_BY_TEMPLATE = {
    "Standard Schreiben": ["MANDANT_NACHNAME", "MANDANT_VORNAME", "KENNZEICHEN", "UNFALL_DATUM"],
    "130 Prozent": ["MANDANT_NACHNAME", "KENNZEICHEN", "UNFALL_DATUM", "REPARATURKOSTEN"],
    "Totalschaden (konkret)": ["MANDANT_NACHNAME", "KENNZEICHEN", "UNFALL_DATUM", "WBW", "RESTWERT"],
    "Konkret unter WBW": ["MANDANT_NACHNAME", "KENNZEICHEN", "UNFALL_DATUM", "REPARATURKOSTEN"],
    "Totalschaden (fiktiv)": ["MANDANT_NACHNAME", "KENNZEICHEN", "UNFALL_DATUM", "WBW", "RESTWERT"],
    "Schreiben Totalschaden": ["MANDANT_NACHNAME", "KENNZEICHEN", "UNFALL_DATUM", "WBW", "RESTWERT"],
}


# -----------------------------
# Verarbeitung
# -----------------------------
if st.button("✅ Schreiben erzeugen", type="primary", disabled=(pdf_file is None)):
    try:
        # 1) Template-Keys
        template_keys = wb.get_template_vars(tpl_name)

        # 2) PDF -> Text (aus Bytes)
        pdf_bytes = pdf_file.read()
        # gx.pdf_to_text erwartet Pfad; wir nutzen hier PyMuPDF direkt für bytes:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pdf_text = "\n".join(doc.load_page(i).get_text("text") for i in range(doc.page_count))

        if len(pdf_text.strip()) < 300:
            st.warning("⚠️ Sehr wenig Text im PDF gefunden. Das sieht nach Scan/OCR-PDF aus. Ohne OCR werden viele Felder leer bleiben.")

        # 3) Extract per Regex
        extracted = gx.extract_all(pdf_text)

        # 4) Derived Fields (WBA, KOSTENSUMME_X, etc.)
        derived = gx.derive_fields(extracted)
        merged = {**extracted, **derived}

        # 5) Context nur für Template-Keys
        ctx = gx.build_context_for_template(template_keys, merged)

        # 6) Optional Strict Mode: prüfe wichtige Keys
        required = REQUIRED_KEYS_BY_TEMPLATE.get(template_label, [])
        missing_required = [k for k in required if not str(merged.get(k, "")).strip() and not str(ctx.get(k, "")).strip()]

        if strict_mode and missing_required:
            st.error(f"Strict-Modus: Wichtige Felder fehlen: {missing_required}")
            st.stop()

        # 7) Render Word
        out_path = wb.render_word(tpl_name, ctx, out_prefix)

        st.success(f"Word erstellt: {out_path.name}")

        with open(out_path, "rb") as f:
            st.download_button(
                "⬇️ Download .docx",
                data=f,
                file_name=out_path.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        # -----------------------------
        # Debug
        # -----------------------------
        if show_debug:
            with st.expander("🔎 Debug: Extrahierte Werte", expanded=True):
                st.subheader("Extracted (Regex)")
                st.json(extracted)

                st.subheader("Derived (berechnet)")
                st.json(derived)

            with st.expander("🧩 Debug: Template Keys & fehlende Werte", expanded=False):
                missing_in_context = [k for k in sorted(template_keys) if not str(ctx.get(k, "")).strip()]
                st.write("Keys in Template:", sorted(template_keys))
                st.write("Fehlende Keys im Context:", missing_in_context)

                if missing_required:
                    st.warning(f"Wichtige Keys (für diese Vorlage) fehlen: {missing_required}")

            with st.expander("📦 Debug: Finaler Context (was wirklich in Word geht)", expanded=False):
                st.json(ctx)

        st.caption(f"Gespeichert in: {wb.OUTPUT_DIR}")

    except Exception as e:
        st.error(f"Fehler: {e}")
