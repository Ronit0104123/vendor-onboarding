"""Deterministic format checks for Indian identifiers. No LLM involved."""
from app.validators.rules import countries, matches, state_codes

GSTIN_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def is_valid_pan(pan: str) -> bool:
    return matches(countries()["IN"]["tax_ids"]["PAN"]["pattern"], pan)


def is_valid_gstin_format(gstin: str) -> bool:
    return matches(countries()["IN"]["tax_ids"]["GSTIN"]["pattern"], gstin)


def gstin_check_char(first_14: str) -> str:
    """The GSTN checksum: a base-36 Luhn-style mod.

    Each of the first 14 characters is converted to its base-36 value and multiplied
    by 1 or 2 alternately. Each product is folded (quotient + remainder by 36) and summed.
    The check character is whatever brings the sum up to a multiple of 36.
    """
    total = 0
    for position, char in enumerate(first_14):
        factor = 1 if position % 2 == 0 else 2
        product = GSTIN_ALPHABET.index(char) * factor
        total += product // 36 + product % 36
    return GSTIN_ALPHABET[(36 - total % 36) % 36]


def has_valid_gstin_checksum(gstin: str) -> bool:
    if not is_valid_gstin_format(gstin):
        return False
    return gstin[14] == gstin_check_char(gstin[:14])


def pan_inside_gstin(gstin: str) -> str:
    """Characters 3-12 of a GSTIN are the holder's PAN."""
    return gstin[2:12]


def state_code_of_gstin(gstin: str) -> str:
    return gstin[:2]


def state_code_for(state_name: str) -> str | None:
    return state_codes().get((state_name or "").strip().lower())


def is_valid_ifsc(ifsc: str) -> bool:
    return matches(countries()["IN"]["bank_code"]["pattern"], ifsc)


def is_valid_pin(pin: str) -> bool:
    return matches(countries()["IN"]["postal_code"]["pattern"], pin)
