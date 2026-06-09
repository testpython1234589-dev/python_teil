from __future__ import annotations
from typing import Dict, Any
import re

import gutachten_extractor as gx


def parse_nfz_totalschaden(pages, pdf_source=None) -> Dict[str, Any]:
    full = "\n".join(pages)
    data = {}

    # Versicherung
    data["VERSICHERUNG"] = gx._search_first(
        full,
        [
            r"Versicherter\s+(.+?)\s+VIN",
        ],
    )

    # Fahrzeugtyp
    data["FAHRZEUGTYP"] = gx._search_first(
        full,
        [
            r"Hersteller Modell\s*\n(.+?)\n",
        ],
    )

    # Mandant
    m = re.search(
        r"Anspruchsteller\s*\n(.+?)\nHerr\s+(.+?)\n",
        full,
        re.S,
    )

    if m:
        firma = m.group(1).strip()
        person = m.group(2).strip()

        data["MANDANT_NAME"] = firma
        data["MANDANT_ANREDE"] = "Herr"
        data["MANDANT_VOLLNAME"] = person

        teile = person.split()
        data["MANDANT_VORNAME"] = teile[0]
        data["MANDANT_NACHNAME"] = " ".join(teile[1:])

    # Vorsteuer
    data["VORSTEUERBERECHTIGUNG"] = ""

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
            r"Wiederbeschaffungswert\s*\(regelbesteuert\)\s*([0-9\., ]+)",
        ],
    )

    # Restwert
    data["RESTWERT"] = gx._extract_restwert_robust(full)

    data["_PARSER"] = "nfz_totalschaden"

    return data
