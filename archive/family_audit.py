from dataclasses import dataclass
from sqlite3 import Connection

from desk.budget import family_balance
from registry.lookup import read_family


@dataclass(frozen=True)
class FamilyAudit:
    family_id: str
    limit_bps: int
    published_bps: int
    reserved_bps: int
    available_bps: int


def audit(preparation: Connection, desk: Connection, family_id: str) -> FamilyAudit:
    family = read_family(preparation, family_id)
    balance = family_balance(desk, family.family_id, family.limit_bps)
    return FamilyAudit(family.family_id, family.limit_bps, balance.published_bps,
                       balance.reserved_bps, balance.available_bps)
