from sqlite3 import Connection

from registry.families import FamilyPlan, get_family, require_id
from registry.protocols import TestProtocol, get_protocol


def read_family(db: Connection, family_id: str) -> FamilyPlan:
    require_id(family_id, 'family ID')
    family = get_family(db, family_id)
    if family is None:
        raise KeyError(f'unknown family {family_id!r}')
    return family


def read_registration(db: Connection, test_id: str) -> TestProtocol:
    require_id(test_id, 'test ID')
    protocol = get_protocol(db, test_id)
    if protocol is None:
        raise KeyError(f'unknown test {test_id!r}')
    return protocol
