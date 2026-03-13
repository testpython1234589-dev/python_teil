from __future__ import annotations

import streamlit as st
from typing import Dict, Any, List

import word_backend as wb
import gutachten_extractor as gx

TEMPLATES = {
    "Standard Schreiben": ("vorlage_schreiben-1.docx", "Standard_schreiben"),
    "130 Prozent": ("vorlage_130_prozent-1.docx", "130_prozent"),
    "Totalschaden (konkret)": ("vorlage_totalschaden_konkret-1.docx", "totalschaden_konkret"),
    "Konkret unter WBW": ("vorlage_konkret_unter_wbw-1.docx", "konkret_unter_wbw"),
    "Totalschaden (fiktiv)": ("vorlage_totalschaden_fiktiv-1.docx", "totalschaden_fiktiv"),
    "Schreiben Totalschaden": ("vorlage_schreibentotalschaden-1.docx", "schreibentotalschaden"),
}


def ensure_state():
    st.session_state.setdefault("step", "extract")  # extract -> review
    st.session_state.setdefault("tpl_name", "")
    st.session_state.setdefault("out_prefix", "")
    st.session_state.setdefault("template_label", "")
    st.session_state.setdefault("ctx", {})
    st.session_state.setdefault("template_keys", [])
    st.session_state.setdefault("extracted", {})
    st.session_state.setdefault("derived", {})
    st.session_state.setdefault("pdf_text_len", 0)


def go_review():
    st.session_state["step"] = "review"


def go_extract():
    st.session_state["step"] = "extract"


def render_review_form(keys: List[str], ctx: Dict[str, Any]) -> Dict[str, Any]:
    st.subheader("✅ Überprüfung (alles editierbar)")
    st.caption("Passe Werte an. Danach: Word endgültig erzeugen.")

    updated = dict(ctx)

    priority = [
        "MANDANT_VORNAME", "MANDANT_NACHNAME", "MANDANT_STRASSE", "MANDANT_PLZ_ORT",
        "UNFALL_DATUM", "UNFALL_ORT", "UNFALL_STRASSE",
        "AKTENZEICHEN", "KENNZEICHEN", "FAHRZEUGTYP",
        "VERSICHERUNG", "VER_STRASSE", "VER_ORT",
        "SCHADENSNUMMER", "VORSTEUERBERECHTIGUNG",
        "KOSTENSUMME_X", "WIEDERBESCHAFFUNGSWERTAUFWAND",
        "REPARATURKOSTEN", "WERTMINDERUNG",
    ]

    keys_sorted = []
    for p in priority:
        if p in keys and p not in keys_sorted:
            keys_sorted.append(p)
    for k in keys:
        if k not in keys_sorted:
            keys_sorted.append(k)

    cols = st.columns(3)
    for i, k in enumerate(keys_sorted):
        col = cols[i % 3]
        val = "" if updated.get(k) is None else str(updated.get(k, ""))

        if k in {"SCHADENHERGANG", "SONSTIGE"}:
            updated[k] = col.text_area(k, value=val, height=160, key=f"rev_{k}")
        else:
            updated[k] = col.text_input(k, value=val, key=f"rev_{k}")

    return updated


st.set_page_config(page_title="Gutachten → Schreiben (Review)", layout="wide")
ensure_state()
st.title("Gutachten → Word-Schreiben (ohne KI) + Überprüf-Seite")

with st.expander("📁 Vorlagen im Repo anzeigen", expanded=False):
    st.write(str(wb.VORLAGEN_DIR))
    st.write([p.name for p in wb.VORLAGEN_DIR.glob("*.docx")])


# STEP 1: Extract
if st.session_state["step"] == "extract":
    template_label = st.selectbox("Vorlage wählen", list(TEMPLATES.keys()))
    tpl_name, out_prefix = TEMPLATES[template_label]

    pdf_file = st.file_uploader("Gutachten als PDF hochladen", type=["pdf"])
    show_debug = st.toggle("Debug anzeigen (Blöcke + fehlende Keys)", value=True)

    st.caption("Hinweis: Funktioniert am besten bei Text-PDFs (nicht reine Scans ohne OCR).")

    if st.button("🔎 Werte aus PDF extrahieren", type="primary", disabled=(pdf_file is None)):
        import fitz

        template_keys = sorted(list(wb.get_template_vars(tpl_name)))

        pdf_bytes = pdf_file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pdf_text = "\n".join(doc.load_page(i).get_text("text") for i in range(doc.page_count))

        st.session_state["pdf_text_len"] = len(pdf_text.strip())
        if st.session_state["pdf_text_len"] < 300:
            st.warning("⚠️ Sehr wenig Text im PDF gefunden. Das sieht nach Scan/OCR-PDF aus. Ohne OCR werden viele Felder leer bleiben.")

        extracted = gx.extract_all(pdf_text)
        derived = gx.derive_fields(extracted)
        merged = {**extracted, **derived}

        ctx = gx.build_context_for_template(set(template_keys), merged)
        missing = [k for k in template_keys if not str(ctx.get(k, "")).strip()]

        st.session_state["tpl_name"] = tpl_name
        st.session_state["out_prefix"] = out_prefix
        st.session_state["template_label"] = template_label
        st.session_state["template_keys"] = template_keys
        st.session_state["ctx"] = ctx
        st.session_state["extracted"] = extracted
        st.session_state["derived"] = derived

        if show_debug:
            with st.expander("🔎 Debug: Extracted + Derived", expanded=True):
                st.subheader("Extracted (Regex, block-sicher)")
                st.json(extracted)
                st.subheader("Derived (berechnet)")
                st.json(derived)
            with st.expander("🧩 Debug: Fehlende Keys im Context", expanded=False):
                st.write(missing)

        go_review()
        st.rerun()

# STEP 2: Review + Generate
else:
    st.subheader(f"Vorlage: {st.session_state['template_label']}")
    st.caption(f"PDF-Textlänge: {st.session_state['pdf_text_len']} Zeichen")

    updated_ctx = render_review_form(st.session_state["template_keys"], st.session_state["ctx"])
    st.session_state["ctx"] = updated_ctx

    st.divider()
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("⬅️ Zurück (neu extrahieren)"):
            go_extract()
            st.rerun()

    with c2:
        if st.button("🔄 Review zurücksetzen"):
            template_keys = set(st.session_state["template_keys"])
            merged = {**st.session_state["extracted"], **st.session_state["derived"]}
            st.session_state["ctx"] = gx.build_context_for_template(template_keys, merged)
            st.rerun()

    with c3:
        if st.button("✅ Word endgültig erzeugen", type="primary"):
            out_path = wb.render_word(
                st.session_state["tpl_name"],
                st.session_state["ctx"],
                st.session_state["out_prefix"]
            )

            st.success(f"Word erstellt: {out_path.name}")
            with open(out_path, "rb") as f:
                st.download_button(
                    "⬇️ Download .docx",
                    data=f,
                    file_name=out_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )

            st.caption(f"Gespeichert in: {wb.OUTPUT_DIR}")
