import re

VALID_UZB_PREFIXES = {
    '90', '91',  # Beeline
    '93', '94',  # Ucell
    '95', '99',  # UzMobile
    '97', '88',  # Mobiuz
    '98',  # Perfectum
    '33',  # Humans
    '20',  # OQ
}


def validate_phone_number(phone: str) -> str:
    digits = re.sub(r'\D', '', phone)

    if digits.startswith('998'):
        digits = digits[3:]
    elif digits.startswith('+998'):
        digits = digits[4:]
    elif len(digits) > 9 and digits.startswith('9'):
        digits = digits[-9:]

    if len(digits) != 9:
        raise ValueError("Invalid phone number.")

    prefix = digits[:2]
    if prefix not in VALID_UZB_PREFIXES:
        raise ValueError(f"Invalid operator prefix: {prefix}")

    return f'998{digits}'
