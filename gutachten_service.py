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

    if gutachter_key == "schnur":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)

        extracted = sx.parse_schnur(
            pages,
            pdf_source=pdf_bytes,
        )

        derived = derive_with_existing_logic(extracted)

        return {**extracted, **derived}


    if gutachter_key == "stotko":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)

        extracted = stx.parse_stotko(
            pages,
            pdf_source=pdf_bytes,
        )

        derived = derive_with_existing_logic(extracted)

        return {**extracted, **derived}


    if gutachter_key == "nfz_standard":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)

        extracted = ns.parse_nfz_standard(
            pages,
            pdf_source=pdf_bytes,
        )

        extracted["_PARSER"] = "nfz_standard"

        derived = derive_with_existing_logic(extracted)

        return {**extracted, **derived}


    if gutachter_key == "nfz_totalschaden":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)

        extracted = nt.parse_nfz_totalschaden(
            pages,
            pdf_source=pdf_bytes,
        )

        extracted["_PARSER"] = "nfz_totalschaden"

        derived = derive_with_existing_logic(extracted)

        return {**extracted, **derived}


    return gx.extract_from_pdf_bytes(pdf_bytes)


def derive_with_existing_logic(extracted: Dict[str, Any]) -> Dict[str, Any]:
    return gx.derive_fields(extracted)


def build_context(template_keys: set[str], extracted: Dict[str, Any]) -> Dict[str, Any]:
    return gx.build_context_for_template(template_keys, extracted)


def extract_from_pdf_bytes(pdf_bytes: bytes, gutachter_key: str) -> Dict[str, Any]:
    if gutachter_key == "schnur":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)
        extracted = sx.parse_schnur(pages, pdf_source=pdf_bytes)
        derived = derive_with_existing_logic(extracted)
        return {**extracted, **derived}
    if gutachter_key == "stotko":
        text = gx.pdf_to_text(pdf_bytes)
        pages = gx._split_pages(text)
        extracted = stx.parse_stotko(pages, pdf_source=pdf_bytes)
        derived = derive_with_existing_logic(extracted)
        return {**extracted, **derived}

    return gx.extract_from_pdf_bytes(pdf_bytes)
