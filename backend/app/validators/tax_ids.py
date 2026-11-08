"""Country-aware checks driven entirely by config/countries.yaml."""
from app.validators.rules import countries, matches


def is_supported_country(country: str) -> bool:
    return country in countries()


def tax_id_rules(country: str) -> dict:
    """e.g. {"PAN": {...}, "GSTIN": {...}} for IN."""
    return countries()[country]["tax_ids"]


def is_valid_tax_id(country: str, id_type: str, value: str) -> bool:
    rule = tax_id_rules(country).get(id_type)
    return rule is not None and matches(rule["pattern"], value)


def which_country_matches(id_value: str) -> list[str]:
    """Used for the 'you said UK but this looks like an Indian GSTIN' hint."""
    hits = []
    for code, country in countries().items():
        for id_type, rule in country["tax_ids"].items():
            if matches(rule["pattern"], id_value):
                hits.append(f"{rule['label']} ({country['name']})")
    return hits


def is_valid_postal_code(country: str, value: str) -> bool:
    return matches(countries()[country]["postal_code"]["pattern"], value)


def is_valid_bank_code(country: str, value: str) -> bool:
    return matches(countries()[country]["bank_code"]["pattern"], value)


def required_documents(country: str) -> list[str]:
    return countries()[country]["required_documents"]
