from __future__ import annotations

import streamlit as st
from typing import Dict, Any, List

import word_backend as wb
import gutachten_service as gs
import word_mahnung as wm
import handakte_backend as hb


# ---------------------------------------------------------------------------
# Vorlagen / Gutachter
# ---------------------------------------------------------------------------

TEMPLATES = {
    "gutachterexpress": {
        "Standard Schreiben": (
            "vorlage_schreiben-1-express.docx",
            "Standard_schreiben",
        ),
        "Schreiben Totalschaden": (
            "vorlage_schreibentotalschaden-1-express.docx",
            "schreibentotalschaden",
        ),

        # NFZ-Varianten
        "Nutzfahrzeuge Standard": (
            "vorlage_schreiben-1-express.docx",
            "nfz_standard",
        ),
        "Nutzfahrzeuge Totalschaden": (
            "vorlage_schreibentotalschaden-1-express.docx",
            "nfz_totalschaden",
        ),
    },

    "schnur": {
        "Standard Schreiben": (
            "vorlage_schreiben-1-schnur.docx",
            "Standard_schreiben_schnur",
        ),
        "Schreiben Totalschaden": (
            "vorlage_schreibentotalschaden-1-schnur.docx",
            "schreibentotalschaden_schnur",
        ),
    },

    "stotko": {
        "Standard Schreiben": (
            "vorlage_schreiben-1-stotko.docx",
            "Standard_schreiben_stotko",
        ),
        "Schreiben Totalschaden": (
            "vorlage_schreibentotalschaden-1-stotko.docx",
            "schreibentotalschaden_stotko",
        ),
    },
}


GUTACHTER = {
    "GutachterExpress": "gutachterexpress",
    "Schnur": "schnur",
    "Stotko": "stotko",
}


# ---------------------------------------------------------------------------
# Session State
# ---------------------------------------------------------------------------

def ensure_state() -> None:
    st.session_state.setdefault("step", "extract")
    st.session_state.setdefault("tpl_name", "")
    st.session_state.setdefault("out_prefix", "")
    st.session_state.setdefault("template_label", "")
    st.session_state.setdefault("ctx", {})
    st.session_state.setdefault("template_keys", [])
    st.session_state.setdefault("extracted", {})
    st.session_state.setdefault("debug_extracted", {})
    st.session_state.setdefault("hinweis_button_clicked", False)

    # NEU: Original-PDF speichern, damit handakte_backend.py
    # daraus Telefon, E-Mail und IBAN aus den letzten Seiten lesen kann.
    st.session_state.setdefault("pdf_bytes", b"")


def clear_review_widget_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("rev_"):
            del st.session_state[key]

    st.session_state["hinweis_button_clicked"] = False


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

        # NEU: gespeicherte PDF-Bytes löschen
        st.session_state["pdf_bytes"] = b""

        clear_review_widget_state()


# ---------------------------------------------------------------------------
# Review Formular
# ---------------------------------------------------------------------------

def render_review_form(keys: List[str], ctx: Dict[str, Any]) -> Dict[str, Any]:
    st.subheader("✅ Überprüfung - alle Werte editierbar")
    st.caption("Passe Werte bei Bedarf an. Danach Word endgültig erzeugen.")

    updated = dict(ctx)

    priority = [
        "MANDANT_ANREDE",
        "MANDANT_VORNAME",
        "MANDANT_NACHNAME",
        "MANDANT_NAME",
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
        "VER_STR",
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

        "GENDERN",
        "GENDERN1",
        "GENDERN2",

        "HEUTEDATUM",
        "HEUTDATUM",
        "FRIST_DATUM",

        "SCHADENHERGANG",
        "HINWEIS",
    ]

    visible_keys = (
        set(keys)
        | {k for k, v in ctx.items() if str(v).strip()}
        | {
            "SCHADENSNUMMER",
            "HINWEIS",
            "VORSTEUERBERECHTIGUNG",
            "MANDANT_NAME",
            "VER_STR",
        }
    )

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

        if k == "HINWEIS":
            with col:
                if st.session_state["hinweis_button_clicked"]:
                    st.markdown(
                        "<div style='padding:6px;border-radius:6px;background:#d4edda;"
                        "color:#155724;font-weight:bold;'>Hinweis eingefügt</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        "<div style='padding:6px;border-radius:6px;background:#f8d7da;"
                        "color:#721c24;font-weight:bold;'>Hinweis fehlt</div>",
                        unsafe_allow_html=True,
                    )

                if st.button("Hinweis einfügen", key="btn_hinweis"):
                    st.session_state[widget_key] = (
                        "Hinweis im Hinblick Schadenserweiterung "
                        "(Nutzungsausfall/Mietwagen): Mein Mandant ist nicht in der Lage, "
                        "den immensen Schaden vorzufinanzieren, sondern erst, wenn er den "
                        "Schadensbetrag rasch erhält. Sofern Sie hier konkrete Nachweise "
                        "benötigen, lassen Sie es unbedingt wissen."
                    )
                    st.session_state["hinweis_button_clicked"] = True
                    st.rerun()

                st.text_area(k, height=120, key=widget_key)

        elif k in {"SCHADENHERGANG", "SONSTIGE"}:
            col.text_area(k, height=160, key=widget_key)
        else:
            col.text_input(k, key=widget_key)

        updated[k] = st.session_state[widget_key]

    return updated


# ---------------------------------------------------------------------------
# App Start
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Gutachten → Schreiben", layout="wide")
ensure_state()

st.title("Gutachten → Word-Schreiben")

gutachter_label = st.selectbox("Gutachter wählen", list(GUTACHTER.keys()))
gutachter_key = GUTACHTER[gutachter_label]

available_templates = TEMPLATES[gutachter_key]
template_label = st.selectbox("Vorlage wählen", list(available_templates.keys()))
tpl_name, out_prefix = available_templates[template_label]

pdf_file = st.file_uploader("Gutachten als PDF hochladen", type=["pdf"])
show_debug = st.toggle("Debug anzeigen - extrahierte Werte", value=True)


# ---------------------------------------------------------------------------
# Schritt 1: Extraktion
# ---------------------------------------------------------------------------

if st.session_state["step"] == "extract":
    if st.button("🔎 Werte aus PDF extrahieren", type="primary", disabled=(pdf_file is None)):
        try:
            pdf_bytes = pdf_file.read()

            # NEU: PDF-Bytes speichern für Handakte
            st.session_state["pdf_bytes"] = pdf_bytes

            extracted = gs.extract_from_pdf_bytes(
                pdf_bytes,
                gutachter_key,
                template_label,
            )

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

            review_keys = list(
                set(template_keys)
                | {k for k, v in ctx.items() if str(v).strip()}
                | {
                    "SCHADENSNUMMER",
                    "HINWEIS",
                    "VORSTEUERBERECHTIGUNG",
                    "MANDANT_NAME",
                    "VER_STR",
                }
            )

            load_review_widget_state(review_keys, ctx)

            go_review()
            st.rerun()

        except Exception as e:
            st.error(f"❌ Fehler bei Extraktion: {e}")


# ---------------------------------------------------------------------------
# Schritt 2: Review + Downloads
# ---------------------------------------------------------------------------

else:
    st.subheader(f"Vorlage: {st.session_state['template_label']}")

    if show_debug:
        with st.expander("🔎 Debug: Extrahierte Rohwerte", expanded=False):
            st.json(st.session_state.get("debug_extracted", {}))

    updated_ctx = render_review_form(
        st.session_state["template_keys"],
        st.session_state["ctx"],
    )

    st.session_state["ctx"] = updated_ctx

    st.divider()

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("⬅️ Zurück - neu extrahieren"):
            go_extract(clear_all=True)
            st.rerun()

    with c2:
        if st.button("🔄 Review zurücksetzen"):
            try:
                template_keys = set(st.session_state["template_keys"])

                ctx = gs.build_context(
                    template_keys,
                    st.session_state["extracted"],
                )

                st.session_state["ctx"] = ctx

                clear_review_widget_state()

                review_keys = list(
                    set(st.session_state["template_keys"])
                    | {k for k, v in ctx.items() if str(v).strip()}
                    | {
                        "SCHADENSNUMMER",
                        "HINWEIS",
                        "VORSTEUERBERECHTIGUNG",
                        "MANDANT_NAME",
                        "VER_STR",
                    }
                )

                load_review_widget_state(review_keys, ctx)

                st.rerun()

            except Exception as e:
                st.error(f"❌ Fehler beim Zurücksetzen: {e}")

    with c3:
        if st.button("✅ Word endgültig erzeugen", type="primary"):

            # Aktuelle Werte + Rohwerte zusammenführen.
            # Manuelle Änderungen aus ctx haben Vorrang.
            merged = {
                **st.session_state.get("extracted", {}),
                **st.session_state.get("ctx", {}),
            }

            # ── 1. Normales Schreiben ─────────────────────────────────────
            try:
                out_path = wb.render_word(
                    st.session_state["tpl_name"],
                    st.session_state["ctx"],
                    st.session_state["out_prefix"],
                )

                st.success(f"✅ Schreiben erstellt: {out_path.name}")

                with open(out_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download Schreiben",
                        data=f.read(),
                        file_name=out_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_schreiben",
                    )

            except Exception as e:
                st.error(f"❌ Fehler beim normalen Schreiben: {e}")

            # ── 2. Mahnungsschreiben ──────────────────────────────────────
            try:
                mahnung_path = wm.render_mahnung(merged)

                st.success(f"✅ Mahnung erstellt: {mahnung_path.name}")

                with open(mahnung_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download Mahnung",
                        data=f.read(),
                        file_name=mahnung_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_mahnung",
                    )

            except FileNotFoundError as e:
                st.warning(f"⚠️ Mahnung nicht erstellt: {e}")
            except Exception as e:
                st.error(f"❌ Fehler bei Mahnung: {e}")

            # ── 3. Handakte ───────────────────────────────────────────────
            try:
                handakte_path = hb.render_handakte_docx(
                    data=merged,

                    # NEU: PDF-Bytes an Handaktenmodul übergeben.
                    # Dadurch kann handakte_backend.py Telefon, E-Mail und IBAN
                    # aus den letzten PDF-Seiten extrahieren.
                    pdf_bytes=st.session_state.get("pdf_bytes", b""),

                    template_path="handakte_gutachten.docx",
                    output_dir="generated",
                )

                st.success(f"✅ Handakte erstellt: {handakte_path.name}")

                with open(handakte_path, "rb") as f:
                    st.download_button(
                        "⬇️ Download Handakte",
                        data=f.read(),
                        file_name=handakte_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_handakte",
                    )

            except FileNotFoundError as e:
                st.warning(f"⚠️ Handakte nicht erstellt: {e}")
            except Exception as e:
                st.error(f"❌ Fehler bei Handakte: {e}")

            st.caption(f"Gespeichert in: {wb.OUTPUT_DIR}")
