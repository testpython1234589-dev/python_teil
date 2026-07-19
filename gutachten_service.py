from __future__ import annotations

from typing import Dict, Any
import re

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

    text = gx.pdf_to_text(pdf_bytes)
    pages = gx._split_pages(text)

    if gutachter_key == "schnur":
        extracted = sx.parse_schnur(
            pages,
            pdf_source=pdf_bytes,
        )
        return recalculate_after_manual_edit(extracted)

    if gutachter_key == "stotko":
        extracted = stx.parse_stotko(
            pages,
            pdf_source=pdf_bytes,
        )
        return recalculate_after_manual_edit(extracted)

    if gutachter_key == "gutachterexpress":

        if template_label == "Nutzfahrzeuge Standard":
            extracted = ns.parse_nfz_standard(
                pages,
                pdf_source=pdf_bytes,
            )

            extracted["_PARSER"] = "nfz_standard"
            extracted["_PARSER_VARIANTE"] = "reparaturschaden"

            return recalculate_after_manual_edit(extracted)

        if template_label == "Nutzfahrzeuge Totalschaden":
            extracted = nt.parse_nfz_totalschaden(
                pages,
                pdf_source=pdf_bytes,
            )

            extracted["_PARSER"] = "nfz_totalschaden"
            extracted["_PARSER_VARIANTE"] = "totalschaden"

            return recalculate_after_manual_edit(extracted)

        return gx.extract_from_pdf_bytes(pdf_bytes)

    return gx.extract_from_pdf_bytes(pdf_bytes)


def derive_with_existing_logic(extracted: Dict[str, Any]) -> Dict[str, Any]:
    return gx.derive_fields(extracted)


def _same_money(a: Any, b: Any) -> bool:
    """
    Vergleicht Geldwerte stabil:
    7.855,04 € == 7855.04
    """
    da = gx._parse_money(str(a or ""))
    db = gx._parse_money(str(b or ""))

    if da is not None and db is not None:
        return da == db

    return str(a or "").strip() == str(b or "").strip()


def recalculate_after_manual_edit(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Wird nach manueller Prüfung/Änderung genutzt.

    Wichtig:
    - Manuell geänderte Werte bleiben erhalten.
    - Leere Felder überschreiben keine echten Werte.
    - NFZ-Totalschaden nutzt bei Vorsteuer Ja netto.
    - NFZ-Totalschaden nutzt bei Vorsteuer Nein brutto.
    """

    base = dict(data)

    if base.get("_PARSER") == "nfz_totalschaden":
        base = apply_nfz_totalschaden_value_logic(base)

    derived = gx.derive_fields(base)
    result = {**base, **derived}

    if base.get("_PARSER") == "nfz_totalschaden":
        result = fix_nfz_totalschaden_after_derive(result, base)

    if base.get("_PARSER") == "nfz_standard":
        result = fix_nfz_standard_after_derive(result, base)

    return result


def apply_nfz_totalschaden_value_logic(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    NFZ-Totalschaden Steuerlogik:

    Vorsteuerabzug Ja:
        WBW_NETTO - RESTWERT_NETTO

    Vorsteuerabzug Nein:
        WBW_BRUTTO - RESTWERT_BRUTTO

    Wichtig:
    Wenn der Nutzer WBW oder RESTWERT manuell geändert hat,
    wird dieser manuelle Wert NICHT wieder durch Netto/Brutto überschrieben.
    """

    d = dict(data)

    vorsteuer = gx._normalize_yes_no(
        str(
            d.get("VORSTEUERABZUG_RAW")
            or d.get("VORSTEUERBERECHTIGUNG")
            or ""
        )
    )

    d["VORSTEUERABZUG_RAW"] = vorsteuer

    wbw = str(d.get("WBW", "") or "").strip()
    restwert = str(d.get("RESTWERT", "") or "").strip()

    wbw_netto = str(d.get("WBW_NETTO", "") or "").strip()
    wbw_brutto = str(d.get("WBW_BRUTTO", "") or "").strip()

    restwert_netto = str(d.get("RESTWERT_NETTO", "") or "").strip()
    restwert_brutto = str(d.get("RESTWERT_BRUTTO", "") or "").strip()

    if vorsteuer == "Ja":
        # Nur automatisch auf netto setzen, wenn WBW leer ist
        # oder aktuell noch der Brutto-Wert drinsteht.
        if not wbw or _same_money(wbw, wbw_brutto):
            d["WBW"] = wbw_netto or wbw or wbw_brutto

        # Manuell geänderten WBW beibehalten
        else:
            d["WBW"] = wbw

        if not restwert or _same_money(restwert, restwert_brutto):
            d["RESTWERT"] = restwert_netto or restwert or restwert_brutto
        else:
            d["RESTWERT"] = restwert

    elif vorsteuer == "Nein":
        # Nur automatisch auf brutto setzen, wenn WBW leer ist
        # oder aktuell noch der Netto-Wert drinsteht.
        if not wbw or _same_money(wbw, wbw_netto):
            d["WBW"] = wbw_brutto or wbw or wbw_netto
        else:
            d["WBW"] = wbw

        if not restwert or _same_money(restwert, restwert_netto):
            d["RESTWERT"] = restwert_brutto or restwert or restwert_netto
        else:
            d["RESTWERT"] = restwert

    return d


def fix_nfz_totalschaden_after_derive(
    result: Dict[str, Any],
    extracted: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Schützt NFZ-Totalschaden-Felder nach gx.derive_fields().
    """

    if extracted.get("_PARSER") != "nfz_totalschaden":
        return result

    result = dict(result)

    protected_keys = [
        "MANDANT_ANREDE",
        "MANDANT_VORNAME",
        "MANDANT_NACHNAME",
        "MANDANT_VOLLNAME",
        "MANDANT_NAME",
        "MANDANT_FIRMA",
        "MANDANT_STRASSE",
        "MANDANT_PLZ_ORT",
        "SCHADENSNUMMER",
        "VERSICHERUNG",
        "VER_STRASSE",
        "VER_ORT",
        "VERSICHERUNGSNUMMER",
        "FAHRZEUGTYP",
        "UNFALL_DATUM",
        "UNFALL_ORT",
        "KENNZEICHEN_MANDANT",
        "EIGENES_KENNZEICHEN",
        "KENNZEICHEN",
        "KENNZEICHEN_GEGNER",
        "SCHADENHERGANG",
        "WBW_BRUTTO",
        "WBW_NETTO",
        "RESTWERT_BRUTTO",
        "RESTWERT_NETTO",
    ]

    for key in protected_keys:
        if extracted.get(key) not in (None, ""):
            result[key] = extracted.get(key)

    result["VRSICHERUNG"] = result.get("VERSICHERUNG", "")

    # Bei Totalschaden ist die Totalschadensumme die relevante Gesamtsumme.
    result["KOSTENSUMME_X"] = result.get("KOSTENSUMME_TOTALSCHADEN", "")

    return result


def fix_nfz_standard_after_derive(
    result: Dict[str, Any],
    extracted: Dict[str, Any],
) -> Dict[str, Any]:
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

    if firma:
        result["MANDANT_NAME"] = firma
        result["MANDANT_FIRMA"] = firma

    if firma and ansprechpartner:
        result["MANDANT_VORNAME"] = f"{ansprechpartner} Geschäftsführer von"
        result["MANDANT_NACHNAME"] = firma
        result["MANDANT_VOLLNAME"] = f"{ansprechpartner} Geschäftsführer von {firma}"
    elif firma:
        result["MANDANT_VORNAME"] = ""
        result["MANDANT_NACHNAME"] = firma
        result["MANDANT_VOLLNAME"] = firma

    result["SCHADENART"] = "Reparaturschaden"
    result["REPARATURSCHADEN"] = "Ja"

    result["WIEDERBESCHAFFUNGSWERTAUFWAND"] = ""
    result["KOSTENSUMME_TOTALSCHADEN"] = ""

    eigenes = str(
        extracted.get("KENNZEICHEN_MANDANT")
        or extracted.get("EIGENES_KENNZEICHEN")
        or extracted.get("KENNZEICHEN")
        or ""
    ).strip()

    result["KENNZEICHEN"] = eigenes
    result["KENNZEICHEN_MANDANT"] = eigenes
    result["EIGENES_KENNZEICHEN"] = eigenes

    gegner = str(extracted.get("KENNZEICHEN_GEGNER") or "").strip()

    def norm_plate(x: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(x or "").upper())

    if not gegner or norm_plate(gegner) == norm_plate(eigenes):
        result["KENNZEICHEN_GEGNER"] = ""
    else:
        result["KENNZEICHEN_GEGNER"] = gegner

    result["KOSTENSUMME_X"] = result.get("KOSTENSUMME_REPARATUR", "")

    if extracted.get("UNFALL_ORT"):
        result["UNFALL_ORT"] = extracted.get("UNFALL_ORT")

    return result


def build_context(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
    return gx.build_context_for_template(template_keys, extracted)
