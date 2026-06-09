from __future__ import annotations
from typing import Dict, Any

import gutachten_extractor as gx


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data = {}

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

    data["REPARATURKOSTEN"] = gx._extract_money(
        full,
        [
            r"Reparaturkosten ohne MwSt\.\s*([0-9\., ]+)",
        ],
    )

    data["WBW"] = gx._extract_money(
        full,
        [
            r"Wiederbeschaffungswert\s*\(regelbesteuert\)\s*([0-9\., ]+)",
        ],
    )

    data["RESTWERT"] = gx._extract_restwert_robust(full)

    return data
