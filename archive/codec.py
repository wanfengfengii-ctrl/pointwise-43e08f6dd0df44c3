import json
from decimal import Decimal
from fractions import Fraction


def rational_parts(value: Fraction) -> dict[str, str]:
    return {
        'numerator': str(Decimal(value.numerator)),
        'denominator': str(Decimal(value.denominator)),
    }


def encode_report_payload(payload: dict) -> str:
    fields = dict(payload)
    for name in ('null_rate', 'p_value'):
        fields[name] = rational_parts(fields[name])
    return json.dumps(fields, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def decode_report_payload(text: str) -> dict:
    fields = json.loads(text)
    for name in ('null_rate', 'p_value'):
        parts = fields[name]
        fields[name] = Fraction(int(Decimal(parts['numerator'])), int(Decimal(parts['denominator'])))
    return fields
