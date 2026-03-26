from __future__ import annotations

import streamlit as st
from typing import Dict, Any, List

import word_backend as wb
import gutachten_service as gs


TEMPLATES = {
    "Standard Schreiben": ("vorlage_schreiben-1.docx", "Standard_schreiben"),
    "130 Prozent": ("vorlage_130_prozent-1.docx", "130_prozent"),
    "Totalschaden (konkret)": ("vorlage_totalschaden_konkret-1.docx", "totalschaden_konkret"),
    "Konkret unter WBW": ("vorlage_konkret_unter_wbw-1.docx", "konkret_unter_wbw"),
    "Totalschaden (fiktiv)": ("vorlage_totalschaden_fiktiv-1.docx", "totalschaden_fiktiv"),
    "Schreiben Totalschaden": ("vorlage_schreibentotalschaden-1.docx", "schreibentotalschaden"),
}

GUTACHTER = {
    "GutachterExpress": "gutachterexpress",
    "Schnur": "schnur",
}


def ensure_state() -> None:
    st.session_state.setdefault("step", "extract")
    st.session_state.setdefault("tpl_name", "")
    st.session_state.setdefault("out_prefix", "")
    st.session_state.setdefault("template_label", "")
    st.session_state.setdefault("ctx", {})
    st.session_state.setdefault("template_keys", [])
    st.session_state.setdefault("extracted", {})
    st.session_state.setdefault("debug_extracted", {})


def clear_review_widget_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("rev_"):
            del st.session_state[key]


def load_review_widget_state(keys: List[str], ctx: Dict[str, Any]) -> None:
    for k in keys:
        st.session_state[f"rev_{k}"] = "" if ctx.get(k) is None else str(ctx.get(k, ""))


def go_review() -> None:
    st.session_state["step"] = "review"


def go_extract(clear_all: bool = False) -> None:
    st.session_state["step"] = "extract"

    if clear_all:
        st.session_state["tpl_name"] = ""
        st.session_state["out_prefix"] = ""
        st.session_state["template_label"] = ""
        st.session_state["ctx"] = {}
        st.session_state["template_keys"] = []
        st.session_state["extracted"] = {}
        st.session_state["debug_extracted"] = {}
        clear_review_widget_state()


def render_review_form(keys: List[str], ctx: Dict[str, Any]) -> Dict[str, Any]:
    st.subheader("✅ Überprüfung (alles editierbar)")
    st.caption("Passe Werte an. Danach: Word endgültig erzeugen.")

    updated = dict(ctx)

    priority = [
        "MANDANT_VORNAME",
        "MANDANT_NACHNAME",
        "MANDANT_STRASSE",
        "MANDANT_PLZ_ORT",
        "UNFALL_DATUM",
        "UNFALL_ORT",
        "UNFALL_STRASSE",
        "AKTENZEICHEN",
        "SCHADENSNUMMER",
        "KENNZEICHEN_MANDANT",
        "KENNZEICHEN_GEGNER",
        "KENNZEICHEN",
        "FAHRZEUGTYP",
        "VERSICHERUNG",
        "VER_STRASSE",
        "VER_ORT",
        "VORSTEUERBERECHTIGUNG",
        "REPARATURKOSTEN",
        "WERTMINDERUNG",
        "WERTVERBESSERUNG",
        "WBW",
        "WIEDERBESCHAFFUNGSWERTAUFWAND",
        "MELDUNGSKOSTEN",
        "ZUSATZKOSTEN_BEZEICHNUNG1",
        "ZUSATZKOSTEN_BETRAG1",
        "ZUSATZKOSTEN_BEZEICHNUNG2",
        "ZUSATZKOSTEN_BETRAG2",
        "ZUSATZKOSTEN_BEZEICHNUNG3",
        "ZUSATZKOSTEN_BETRAG3",
        "KOSTENPAUSCHALE",
        "GUTACHTERKOSTEN",
        "KOSTENSUMME_X",
        "GENDERN1",
        "GENDERN2",
        "HEUTEDATUM",
        "FRIST_DATUM",
        "SCHADENHERGANG",
    ]

    visible_keys = set(keys) | {k for k, v in ctx.items() if str(v).strip()} | {"SCHADENSNUMMER"}

    keys_sorted: List[str] = []

    for p in priority:
        if p in visible_keys and p not in keys_sorted:
            keys_sorted.append(p)

    for k in keys:
        if k in visible_keys and k not in keys_sorted:
            keys_sorted.append(k)

    for k in sorted(visible_keys):
        if k not in keys_sorted:
            keys_sorted.append(k)

    cols = st.columns(3)

    for i, k in enumerate(keys_sorted):
        col = cols[i % 3]
        widget_key = f"rev_{k}"

        if widget_key not in st.session_state:
            st.session_state[widget_key] = "" if ctx.get(k) is None else str(ctx.get(k, ""))

        if k in {"SCHADENHERGANG", "SONSTIGE"}:
            col.text_area(k, height=160, key=widget_key)
        else:
            col.text_input(k, key=widget_key)

        updated[k] = st.session_state[widget_key]

    return updated


st.set_page_config(page_title="Gutachten → Schreiben", layout="wide")
ensure_state()

st.title("Gutachten → Word-Schreiben")

gutachter_label = st.selectbox("Gutachter wählen", list(GUTACHTER.keys()))
gutachter_key = GUTACHTER[gutachter_label]

template_label = st.selectbox("Vorlage wählen", list(TEMPLATES.keys()))
tpl_name, out_prefix = TEMPLATES[template_label]

pdf_file = st.file_uploader("Gutachten als PDF hochladen", type=["pdf"])
show_debug = st.toggle("Debug anzeigen (Extrahierte Werte)", value=True)

if st.session_state["step"] == "extract":
    if st.button("🔎 Werte aus PDF extrahieren", type="primary", disabled=(pdf_file is None)):
        pdf_bytes = pdf_file.read()

        extracted = gs.extract_from_pdf_bytes(pdf_bytes, gutachter_key)
        template_keys = sorted(list(wb.get_template_vars(tpl_name)))
        ctx = gs.build_context(set(template_keys), extracted)

        st.session_state["tpl_name"] = tpl_name
        st.session_state["out_prefix"] = out_prefix
        st.session_state["template_label"] = template_label
        st.session_state["template_keys"] = template_keys
        st.session_state["ctx"] = ctx
        st.session_state["extracted"] = extracted
        st.session_state["debug_extracted"] = extracted

        clear_review_widget_state()
        load_review_widget_state(list(set(template_keys) | {k for k, v in ctx.items() if str(v).strip()} | {"SCHADENSNUMMER"}), ctx)

        go_review()
        st.rerun()

else:
    st.subheader(f"Vorlage: {st.session_state['template_label']}")

    if show_debug:
        with st.expander("🔎 Debug: Extrahierte Werte", expanded=False):
            st.json(st.session_state.get("debug_extracted", {}))

    updated_ctx = render_review_form(
        st.session_state["template_keys"],
        st.session_state["ctx"],
    )
    st.session_state["ctx"] = updated_ctx

    st.divider()
    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("⬅️ Zurück (neu extrahieren)"):
            go_extract(clear_all=True)
            st.rerun()

    with c2:
        if st.button("🔄 Review zurücksetzen"):
            template_keys = set(st.session_state["template_keys"])
            ctx = gs.build_context(
                template_keys,
                st.session_state["extracted"],
            )
            st.session_state["ctx"] = ctx
            clear_review_widget_state()
            load_review_widget_state(
                list(set(st.session_state["template_keys"]) | {k for k, v in ctx.items() if str(v).strip()} | {"SCHADENSNUMMER"}),
                ctx,
            )
            st.rerun()

    with c3:
        if st.button("✅ Word endgültig erzeugen", type="primary"):
            out_path = wb.render_word(
                st.session_state["tpl_name"],
                st.session_state["ctx"],
                st.session_state["out_prefix"],
            )

            st.success(f"Word erstellt: {out_path.name}")

            with open(out_path, "rb") as f:
                data = f.read()

            st.download_button(
                "⬇️ Download .docx",
                data=data,
                file_name=out_path.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

            st.caption(f"Gespeichert in: {wb.OUTPUT_DIR}")
