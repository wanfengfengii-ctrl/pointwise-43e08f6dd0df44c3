from fractions import Fraction
from sqlite3 import Connection

from registry.families import get_family, initialize_families, insert_family, validate_family
from registry.protocols import (
    TestProtocol, get_protocol, initialize_protocols, insert_protocol, validate_protocol,
)


def initialize_registry(db: Connection) -> None:
    initialize_families(db)
    initialize_protocols(db)


def register(db: Connection, family_id: str, limit_bps: int, test_id: str,
             null_rate: Fraction | int, alpha_bps: int) -> TestProtocol:
    family = validate_family(family_id, limit_bps)
    protocol = validate_protocol(test_id, family_id, null_rate, alpha_bps)
    with db:
        db.execute('BEGIN IMMEDIATE')
        previous_family = get_family(db, family_id)
        if previous_family is None:
            insert_family(db, family)
        elif previous_family != family:
            raise ValueError(f'conflicting family limit for {family_id!r}')

        previous = get_protocol(db, test_id)
        if previous is None:
            insert_protocol(db, protocol)
            return protocol
        if previous != protocol:
            raise ValueError(f'conflicting registration for {test_id!r}')
        return previous
