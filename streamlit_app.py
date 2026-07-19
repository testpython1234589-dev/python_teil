from __future__ import annotations

from typing import Dict, Any, List

import streamlit as st

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


EXTRA_REVIEW_KEYS = {
    "SCHADENSNUMMER",
    "HINWEIS",
    "VORSTEUERABZUG_RAW",
    "VORSTEUERBERECHTIGUNG",
    "MANDANT_NAME",
    "MANDANT_FIRMA",
    "MANDANT_VORNAME",
    "MANDANT_NACHNAME",
    "MANDANT_VOLLNAME",
    "VER_STRASSE",
    "VER_STR",
    "WBW",
    "RESTWERT",
    "WBW_BRUTTO",
    "WBW_NETTO",
    "RESTWERT_BRUTTO",
    "RESTWERT_NETTO",
    "REPARATURKOSTEN_NETTO",
    "REPARATURKOSTEN_BRUTTO",
    "REPARATURKOSTEN",
    "GUTACHTERKOSTEN_NETTO",
    "GUTACHTERKOSTEN_BRUTTO",
    "GUTACHTERKOSTEN",
    "MELDUNGSKOSTEN",
    "WIEDERBESCHAFFUNGSWERTAUFWAND",
    "KOSTENSUMME_TOTALSCHADEN",
    "KOSTENSUMME_REPARATUR",
    "KOSTENSUMME_X",
}

HIDDEN_REVIEW_KEYS = {
    "_PARSER",
    "_PARSER_VARIANTE",
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
    st.session_state.setdefault("pdf_bytes", b"")
    st.session_state.setdefault("reload_review_widgets", False)


def clear_review_widget_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("rev_"):
            del st.session_state[key]

    st.session_state["hinweis_button_clicked"] = False


def get_review_keys(template_keys: List[str], ctx: Dict[str, Any]) -> List[str]:
    keys = (
        set(template_keys)
        | {k for k, v in ctx.items() if str(v).strip()}
        | EXTRA_REVIEW_KEYS
    )

    keys = {
        k for k in keys
        if k not in HIDDEN_REVIEW_KEYS
        and not str(k).startswith("_")
    }

    return list(keys)


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
        st.session_state["pdf_bytes"] = b""
        st.session_state["reload_review_widgets"] = False
        clear_review_widget_state()


# ---------------------------------------------------------------------------
# Review / Neuberechnung
# ---------------------------------------------------------------------------

def collect_review_values_safely() -> Dict[str, Any]:
    """
    Holt alle Review-Felder.

    Wichtig:
    Leere Review-Felder überschreiben vorhandene Werte NICHT.
    Sonst verschwinden WBW, Gutachterkosten, Meldekosten usw.
    """

    original = dict(st.session_state.get("extracted", {}))
    current_ctx = dict(st.session_state.get("ctx", {}))

    merged = {
        **original,
        **current_ctx,
    }

    for key in list(st.session_state.keys()):
        if not key.startswith("rev_"):
            continue

        real_key = key.replace("rev_", "", 1)
        value = st.session_state.get(key)
        value_str = "" if value is None else str(value).strip()

        old_value_str = "" if merged.get(real_key) is None else str(merged.get(real_key, "")).strip()

        # Leeres Feld darf vorhandenen Wert NICHT löschen.
        if value_str == "" and old_value_str != "":
            continue

        merged[real_key] = value

    return merged


def recalc_review_values() -> None:
    """
    Nimmt manuelle Änderungen aus dem Review,
    rechnet Kosten/Summen neu
    und aktualisiert ctx + extracted.

    Diese Funktion ist der zentrale Fix:
    Es wird NICHT mehr nur mit dem Word-Kontext gerechnet,
    sondern mit allen extrahierten + manuell bearbeiteten Feldern.
    """

    merged = collect_review_values_safely()

    recalculated = gs.recalculate_after_manual_edit(merged)

    template_keys = set(st.session_state.get("template_keys", []))

    # Word-Kontext bauen
    word_ctx = gs.build_context(template_keys, recalculated)

    # Für Review alle Werte behalten, nicht nur Word-Platzhalter.
    full_ctx = {
        **recalculated,
        **word_ctx,
    }

    st.session_state["extracted"] = recalculated
    st.session_state["debug_extracted"] = recalculated
    st.session_state["ctx"] = full_ctx

    st.session_state["reload_review_widgets"] = True


def reload_review_widgets_if_needed() -> None:
    """
    Lädt Review-Widgets nach Neuberechnung neu.
    Muss passieren, bevor die Widgets gerendert werden.
    """

    if not st.session_state.get("reload_review_widgets"):
        return

    ctx = st.session_state.get("ctx", {})
    template_keys = st.session_state.get("template_keys", [])

    clear_review_widget_state()

    review_keys = get_review_keys(template_keys, ctx)
    load_review_widget_state(review_keys, ctx)

    st.session_state["reload_review_widgets"] = False


# ---------------------------------------------------------------------------
# Review Formular
# ---------------------------------------------------------------------------

def render_review_form(keys: List[str], ctx: Dict[str, Any]) -> Dict[str, Any]:
    st.subheader("✅ Überprüfung - alle Werte editierbar")
    st.caption("Passe Werte bei Bedarf an. Danach Werte neu berechnen oder Word endgültig erzeugen.")

    updated = {
        **st.session_state.get("extracted", {}),
        **ctx,
    }

    priority = [
        "MANDANT_ANREDE",
        "MANDANT_VORNAME",
        "MANDANT_NACHNAME",
        "MANDANT_VOLLNAME",
        "MANDANT_NAME",
        "MANDANT_FIRMA",
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
        "EIGENES_KENNZEICHEN",
        "FAHRZEUGTYP",
        "VERSICHERUNG",
        "VER_STRASSE",
        "VER_STR",
        "VER_ORT",
        "VERSICHERUNGSNUMMER",
        "VORSTEUERABZUG_RAW",
        "VORSTEUERBERECHTIGUNG",
        "REPARATURKOSTEN_NETTO",
        "REPARATURKOSTEN_BRUTTO",
        "REPARATURKOSTEN",
        "REPARATURSCHADEN",
        "WERTMINDERUNG",
        "WERTVERBESSERUNG",
        "WBW",
        "RESTWERT",
        "WBW_BRUTTO",
        "WBW_NETTO",
        "RESTWERT_BRUTTO",
        "RESTWERT_NETTO",
        "WIEDERBESCHAFFUNGSWERTAUFWAND",
        "MELDUNGSKOSTEN",
        "ZUSATZKOSTEN_BEZEICHNUNG1",
        "ZUSATZKOSTEN_BETRAG1",
        "ZUSATZKOSTEN_BEZEICHNUNG2",
        "ZUSATZKOSTEN_BETRAG2",
        "ZUSATZKOSTEN_BEZEICHNUNG3",
        "ZUSATZKOSTEN_BETRAG3",
        "KOSTENPAUSCHALE",
        "GUTACHTERKOSTEN_NETTO",
        "GUTACHTERKOSTEN_BRUTTO",
        "GUTACHTERKOSTEN",
        "KOSTENSUMME_REPARATUR",
        "KOSTENSUMME_TOTALSCHADEN",
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
        | {k for k, v in updated.items() if str(v).strip()}
        | EXTRA_REVIEW_KEYS
    )

    visible_keys = {
        k for k in visible_keys
        if k not in HIDDEN_REVIEW_KEYS
        and not str(k).startswith("_")
    }

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
            st.session_state[widget_key] = "" if updated.get(k) is None else str(updated.get(k, ""))

        if k == "HINWEIS":
            with col:
                if str(st.session_state.get(widget_key, "")).strip():
                    st.success("Hinweis eingefügt")
                else:
                    st.warning("Hinweis fehlt")

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

    if st.button("Werte aus PDF extrahieren", type="primary", disabled=(pdf_file is None)):
        try:
            pdf_bytes = pdf_file.read()

            st.session_state["pdf_bytes"] = pdf_bytes

            extracted = gs.extract_from_pdf_bytes(
                pdf_bytes,
                gutachter_key,
                template_label,
            )

            template_keys = sorted(list(wb.get_template_vars(tpl_name)))
            word_ctx = gs.build_context(set(template_keys), extracted)

            # Wichtig:
            # ctx enthält alle Werte, nicht nur Word-Platzhalter.
            full_ctx = {
                **extracted,
                **word_ctx,
            }

            st.session_state["tpl_name"] = tpl_name
            st.session_state["out_prefix"] = out_prefix
            st.session_state["template_label"] = template_label
            st.session_state["template_keys"] = template_keys
            st.session_state["ctx"] = full_ctx
            st.session_state["extracted"] = extracted
            st.session_state["debug_extracted"] = extracted
            st.session_state["reload_review_widgets"] = False

            clear_review_widget_state()

            review_keys = get_review_keys(template_keys, full_ctx)
            load_review_widget_state(review_keys, full_ctx)

            go_review()
            st.rerun()

        except Exception as e:
            st.error(f"❌ Fehler bei Extraktion: {e}")


# ---------------------------------------------------------------------------
# Schritt 2: Review + Downloads
# ---------------------------------------------------------------------------

else:
    reload_review_widgets_if_needed()

    st.subheader(f"Vorlage: {st.session_state['template_label']}")

    if show_debug:
        with st.expander("Debug: Extrahierte / berechnete Werte", expanded=False):
            st.json(st.session_state.get("debug_extracted", {}))

    updated_ctx = render_review_form(
        st.session_state["template_keys"],
        st.session_state["ctx"],
    )

    st.session_state["ctx"] = updated_ctx

    st.divider()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button("⬅️ Zurück - neu extrahieren"):
            go_extract(clear_all=True)
            st.rerun()

    with c2:
        if st.button("Review zurücksetzen"):
            try:
                template_keys = set(st.session_state["template_keys"])

                word_ctx = gs.build_context(
                    template_keys,
                    st.session_state["extracted"],
                )

                full_ctx = {
                    **st.session_state["extracted"],
                    **word_ctx,
                }

                st.session_state["ctx"] = full_ctx
                st.session_state["reload_review_widgets"] = True
                st.rerun()

            except Exception as e:
                st.error(f"❌ Fehler beim Zurücksetzen: {e}")

    with c3:
        if st.button("🔄 Werte neu berechnen"):
            try:
                recalc_review_values()
                st.success("Werte wurden neu berechnet.")
                st.rerun()

            except Exception as e:
                st.error(f"❌ Fehler beim Neuberechnen: {e}")

    with c4:
        if st.button("✅ Word endgültig erzeugen", type="primary"):

            try:
                # Direkt vor Word-Erstellung nochmal neu berechnen.
                recalc_review_values()

                template_keys = set(st.session_state["template_keys"])
                extracted = st.session_state["extracted"]

                word_ctx = gs.build_context(template_keys, extracted)

                merged = {
                    **extracted,
                    **word_ctx,
                }

                # ── 1. Normales Schreiben ─────────────────────────────────
                try:
                    out_path = wb.render_word(
                        st.session_state["tpl_name"],
                        word_ctx,
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

                # ── 2. Mahnungsschreiben ──────────────────────────────────
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

                # ── 3. Handakte ───────────────────────────────────────────
                try:
                    handakte_path = hb.render_handakte_docx(
                        data=merged,
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

            except Exception as e:
                st.error(f"❌ Fehler bei Word-Erstellung: {e}")
