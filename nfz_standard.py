from __future__ import annotations
from typing import Dict, Any

import gutachten_extractor as gx


def parse_nfz_standard(pages, pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data = {}

    # Name
    raw_name = gx._search_first(
        full,
        [
            r"Anspruchsteller\s+(.+?)\nHerr\b",
            r"Anspruchsteller\s+(.+?)\n(?:Straße|PLZ Ort)",
        ],
    )

    anrede, clean_name = gx._cleanup_name(raw_name)

    data["MANDANT_ANREDE"] = anrede
    data["MANDANT_NAME"] = clean_name

    # Reparaturkosten
    data["REPARATURKOSTEN"] = gx._extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.\s*([0-9\., ]+)",
        ],
    )

    # Wiederbeschaffungswert
    data["WBW"] = gx._extract_money(
        full,
        [
            r"Wiederbeschaffungswert\s*\(steuerneutral\)\s*([0-9\., ]+)",
        ],
    )

    # Kein Restwert bei Standard
    data["RESTWERT"] = ""

    return data
