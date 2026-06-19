from __future__ import annotations

from typing import Dict, Any

import re

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

    extracted = ns.parse_nfz_standard(
        pages,
        pdf_source=pdf_bytes,
    )
    
    extracted["_PARSER"] = "nfz_standard"
    extracted["_PARSER_VARIANTE"] = "reparaturschaden"
    
    derived = derive_with_existing_logic(extracted)
    
    result = {**extracted, **derived}
    
    result = fix_nfz_standard_after_derive(result, extracted)
    
    return result

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

def fix_nfz_standard_after_derive(result: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Korrigiert nur NFZ Standard / Reparaturschaden nach gx.derive_fields().
    Alles andere bleibt unverändert.
    """
    if extracted.get("_PARSER") != "nfz_standard":
        return result

    result = dict(result)

    firma = str(
        extracted.get("MANDANT_FIRMA")
        or extracted.get("MANDANT_NAME")
        or ""
    ).strip()

    ansprechpartner = str(
        extracted.get("ANSPRECHPARTNER_NAME")
        or " ".join(
            x for x in [
                extracted.get("ANSPRECHPARTNER_VORNAME", ""),
                extracted.get("ANSPRECHPARTNER_NACHNAME", ""),
            ]
            if x
        )
        or " ".join(
            x for x in [
                extracted.get("MANDANT_VORNAME", ""),
                extracted.get("MANDANT_NACHNAME", ""),
            ]
            if x
        )
    ).strip()

    # Mandant/Firma schützen
    if firma:
        result["MANDANT_NAME"] = firma
        result["MANDANT_FIRMA"] = firma

    # Deine gewünschte Schreibweise:
    # {{MANDANT_VORNAME}} {{MANDANT_NACHNAME}}
    # => Berthold Richter Geschäftsführer von Kraftverkehr Leipzig GmbH
    if firma and ansprechpartner:
        result["MANDANT_VORNAME"] = f"{ansprechpartner} Geschäftsführer von"
        result["MANDANT_NACHNAME"] = firma
        result["MANDANT_VOLLNAME"] = f"{ansprechpartner} Geschäftsführer von {firma}"
    elif firma:
        result["MANDANT_VORNAME"] = ""
        result["MANDANT_NACHNAME"] = firma
        result["MANDANT_VOLLNAME"] = firma

    # Reparaturschaden ist Status, kein Geldbetrag
    result["SCHADENART"] = "Reparaturschaden"
    result["REPARATURSCHADEN"] = "Ja"

    # Reparaturschaden: keine Totalschadenfelder
    result["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""
    result["KOSTENSUMME_TOTALSCHADEN"] = ""

    # Eigenes Kennzeichen
    eigenes = str(
        extracted.get("KENNZEICHEN_MANDANT")
        or extracted.get("EIGENES_KENNZEICHEN")
        or extracted.get("KENNZEICHEN")
        or ""
    ).strip()

    result["KENNZEICHEN"] = eigenes
    result["KENNZEICHEN_MANDANT"] = eigenes
    result["EIGENES_KENNZEICHEN"] = eigenes

    # Gegnerkennzeichen darf nicht Mandantenkennzeichen sein
    gegner = str(extracted.get("KENNZEICHEN_GEGNER") or "").strip()

    def norm_plate(x: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(x or "").upper())

    if not gegner or norm_plate(gegner) == norm_plate(eigenes):
        result["KENNZEICHEN_GEGNER"] = ""
    else:
        result["KENNZEICHEN_GEGNER"] = gegner

    # Reparatursumme bleibt die relevante Summe
    result["KOSTENSUMME_X"] = result.get("KOSTENSUMME_REPARATUR", "")

    # Unfallort aus Parser übernehmen, falls vorhanden
    if extracted.get("UNFALL_ORT"):
        result["UNFALL_ORT"] = extracted.get("UNFALL_ORT")

    return result
