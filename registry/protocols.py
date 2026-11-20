from dataclasses import dataclass
from fractions import Fraction
from sqlite3 import Connection

from registry.families import require_id


@dataclass(frozen=True)
class TestProtocol:
    test_id: str
    family_id: str
    null_rate: Fraction
    alpha_bps: int


def validate_protocol(test_id: str, family_id: str, null_rate: Fraction | int,
                      alpha_bps: int) -> TestProtocol:
    require_id(test_id, 'test ID')
    require_id(family_id, 'family ID')
    if type(null_rate) not in (Fraction, int) or not 0 <= null_rate <= 1:
        raise ValueError('null rate must be an exact rational in [0, 1]')
    if type(alpha_bps) is not int or not 1 <= alpha_bps <= 10_000:
        raise ValueError('alpha must be an integer from 1 to 10000')
    return TestProtocol(test_id, family_id, Fraction(null_rate), alpha_bps)


def initialize_protocols(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS protocols (
            test_id TEXT PRIMARY KEY NOT NULL,
            family_id TEXT NOT NULL REFERENCES families(family_id),
            null_numerator TEXT NOT NULL,
            null_denominator TEXT NOT NULL,
            alpha_bps INTEGER NOT NULL CHECK (alpha_bps BETWEEN 1 AND 10000)
        )
    ''')


def insert_protocol(db: Connection, protocol: TestProtocol) -> None:
    rate = protocol.null_rate
    # Text preserves rationals beyond SQLite's signed integer range.
    db.execute('INSERT INTO protocols VALUES (?, ?, ?, ?, ?)', (
        protocol.test_id, protocol.family_id, format(rate.numerator, 'x'),
        format(rate.denominator, 'x'), protocol.alpha_bps,
    ))


def get_protocol(db: Connection, test_id: str) -> TestProtocol | None:
    row = db.execute('''
        SELECT test_id, family_id, null_numerator, null_denominator, alpha_bps
        FROM protocols WHERE test_id = ?
    ''', (test_id,)).fetchone()
    if row is None:
        return None
    test_id, family_id, numerator, denominator, alpha = row
    return TestProtocol(test_id, family_id, Fraction(int(numerator, 16), int(denominator, 16)), alpha)
