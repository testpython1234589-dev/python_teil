from __future__ import annotations

from typing import Dict, Any

import gutachten_extractor as gx
import schnur_extractor as sx


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

    return gx.extract_from_pdf_bytes(pdf_bytes)
