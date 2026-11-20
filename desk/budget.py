from dataclasses import dataclass
from sqlite3 import Connection

from desk.commitments import sum_family_commitments


@dataclass(frozen=True)
class FamilyBalance:
    limit_bps: int
    published_bps: int
    reserved_bps: int

    @property
    def available_bps(self) -> int:
        return self.limit_bps - self.published_bps - self.reserved_bps


def family_balance(db: Connection, family_id: str, limit_bps: int) -> FamilyBalance:
    published, reserved = sum_family_commitments(db, family_id)
    return FamilyBalance(limit_bps, published, reserved)


def fits_balance(balance: FamilyBalance, alpha_bps: int) -> bool:
    return alpha_bps <= balance.available_bps
