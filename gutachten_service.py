from __future__ import annotations

from typing import Dict, Any

import gutachten_extractor as gx
import schnur_extractor as sx
import stotko_extractor as stx
import nfz_standard_extractor as ns
import nfz_totalschaden_extractor as nt


def extract_from_pdf_bytes(
    pdf_bytes: bytes,
    gutachter_key: str,
    template_label: str,
) -> Dict[str, Any]:

    # Schnur
    if gutachter_key == "schnur":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)

        extracted = sx.parse_schnur(
            pages,
            pdf_source=pdf_bytes,
        )

        derived = derive_with_existing_logic(extracted)

        return {**extracted, **derived}

    # Stotko
    if gutachter_key == "stotko":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)

        extracted = stx.parse_stotko(
            pages,
            pdf_source=pdf_bytes,
        )

        derived = derive_with_existing_logic(extracted)

        return {**extracted, **derived}

    # GutachterExpress
    if gutachter_key == "gutachterexpress":

        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)

        if template_label == "Nutzfahrzeuge Standard":

    extracted = ns.parse_nfz_standard(
        pages,
        pdf_source=pdf_bytes,
    )

    extracted["_PARSER"] = "nfz_standard"
    extracted["_PARSER_VARIANTE"] = "reparaturschaden"

    # derive_fields bleibt wie bisher aktiv
    derived = derive_with_existing_logic(extracted)

    result = {**extracted, **derived}

    # ===================================================
    # NFZ-STANDARD / REPARATURSCHADEN: Felder schützen
    # ===================================================
    # derive_fields() ist allgemein und überschreibt sonst:
    # - Firma wird als Person gesplittet
    # - REPARATURSCHADEN wird zu Geldbetrag
    # - Totalschadenfelder werden befüllt
    # - Gegnerkennzeichen wird eigenes Kennzeichen
    protected_keys = [
        "MANDANT_ANREDE",
        "MANDANT_FIRMA",
        "MANDANT_NAME",
        "MANDANT_VORNAME",
        "MANDANT_NACHNAME",
        "MANDANT_TITEL",
        "MANDANT_VOLLNAME",
        "MANDANT_STRASSE",
        "MANDANT_PLZ_ORT",

        "AKTENZEICHEN",
        "RECHNUNGSNUMMER",

        "KENNZEICHEN",
        "KENNZEICHEN_MANDANT",
        "EIGENES_KENNZEICHEN",

        "FAHRZEUGTYP",
        "HERSTELLER",
        "MODELL",
        "VIN",

        "SCHADENART",
        "REPARATURSCHADEN",

        "REPARATURKOSTEN",
        "REPARATURKOSTEN_NETTO",
        "REPARATURKOSTEN_BRUTTO",
        "SCHADENHOEHE_NETTO",
        "SCHADENHOEHE_BRUTTO",

        "WBW",
        "RESTWERT",

        "GUTACHTERKOSTEN",
        "GUTACHTERKOSTEN_NETTO",
        "GUTACHTERKOSTEN_BRUTTO",

        "KOSTENSUMME_REPARATUR",
        "KOSTENSUMME_X",
    ]

    for key in protected_keys:
        if extracted.get(key) not in (None, ""):
            result[key] = extracted.get(key)

    # ===================================================
    # Harte Reparaturschaden-Korrekturen
    # ===================================================

    result["SCHADENART"] = "Reparaturschaden"
    result["REPARATURSCHADEN"] = "Ja"

    # Bei Reparaturschaden dürfen diese Totalschadenfelder leer bleiben
    result["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""
    result["KOSTENSUMME_TOTALSCHADEN"] = ""

    # Im NFZ-Standard-Gutachten ist MER KV 50 das eigene Kennzeichen.
    # Gegnerkennzeichen ist nicht vorhanden.
    result["KENNZEICHEN_GEGNER"] = ""

    result["KENNZEICHEN"] = (
        extracted.get("KENNZEICHEN_MANDANT")
        or extracted.get("EIGENES_KENNZEICHEN")
        or extracted.get("KENNZEICHEN")
        or ""
    )

    result["KENNZEICHEN_MANDANT"] = result["KENNZEICHEN"]
    result["EIGENES_KENNZEICHEN"] = result["KENNZEICHEN"]

    # KOSTENSUMME_X soll bei Reparaturschaden die Reparatursumme sein
    result["KOSTENSUMME_X"] = result.get("KOSTENSUMME_REPARATUR", "")

    return result

        elif template_label == "Nutzfahrzeuge Totalschaden":

            extracted = nt.parse_nfz_totalschaden(
                pages,
                pdf_source=pdf_bytes,
            )

            extracted["_PARSER"] = "nfz_totalschaden"

        else:
            return gx.extract_from_pdf_bytes(pdf_bytes)

        derived = derive_with_existing_logic(extracted)

        return {**extracted, **derived}

    # Standard GutachterExpress
    return gx.extract_from_pdf_bytes(pdf_bytes)


def derive_with_existing_logic(extracted: Dict[str, Any]) -> Dict[str, Any]:
    return gx.derive_fields(extracted)


def build_context(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
    return gx.build_context_for_template(template_keys, extracted)

