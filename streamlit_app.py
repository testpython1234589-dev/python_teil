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
    st.session_state.setdefault("step", "extract")
    st.session_state.setdefault("tpl_name", "")
    st.session_state.setdefault("out_prefix", "")
    st.session_state.setdefault("template_label", "")
    st.session_state.setdefault("ctx", {})
    st.session_state.setdefault("template_keys", [])
    st.session_state.setdefault("extracted", {})


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
        "KOSTENSUMME_X", "REPARATURKOSTEN", "WERTMINDERUNG", "GUTACHTERKOSTEN",
        "SCHADENHERGANG"
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
st.title("Gutachten → Word-Schreiben (ohne KI) + Überprüf-Seite (seitenbasiert)")

template_label = st.selectbox("Vorlage wählen", list(TEMPLATES.keys()))
tpl_name, out_prefix = TEMPLATES[template_label]

pdf_file = st.file_uploader("Gutachten als PDF hochladen", type=["pdf"])
show_debug = st.toggle("Debug anzeigen (Extrahierte Werte)", value=True)

if st.session_state["step"] == "extract":
    if st.button("🔎 Werte aus PDF extrahieren", type="primary", disabled=(pdf_file is None)):
        pdf_bytes = pdf_file.read()

        extracted = gx.extract_from_pdf_bytes(pdf_bytes)
        template_keys = sorted(list(wb.get_template_vars(tpl_name)))
        ctx = gx.build_context_for_template(set(template_keys), extracted)

        st.session_state["tpl_name"] = tpl_name
        st.session_state["out_prefix"] = out_prefix
        st.session_state["template_label"] = template_label
        st.session_state["template_keys"] = template_keys
        st.session_state["ctx"] = ctx
        st.session_state["extracted"] = extracted

        if show_debug:
            with st.expander("🔎 Debug: Extrahierte Werte", expanded=True):
                st.json(extracted)

        go_review()
        st.rerun()

else:
    st.subheader(f"Vorlage: {st.session_state['template_label']}")
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
            st.session_state["ctx"] = gx.build_context_for_template(template_keys, st.session_state["extracted"])
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
