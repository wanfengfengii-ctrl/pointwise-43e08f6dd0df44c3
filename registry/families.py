from dataclasses import dataclass
from sqlite3 import Connection


@dataclass(frozen=True)
class FamilyPlan:
    family_id: str
    limit_bps: int


def validate_family(family_id: str, limit_bps: int) -> FamilyPlan:
    require_id(family_id, 'family ID')
    if type(limit_bps) is not int or not 0 <= limit_bps <= 10_000:
        raise ValueError('family limit must be an integer from 0 to 10000')
    return FamilyPlan(family_id, limit_bps)


def require_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonblank string')


def initialize_families(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS families (
            family_id TEXT PRIMARY KEY NOT NULL,
            limit_bps INTEGER NOT NULL CHECK (limit_bps BETWEEN 0 AND 10000)
        )
    ''')


def insert_family(db: Connection, plan: FamilyPlan) -> None:
    db.execute('INSERT INTO families VALUES (?, ?)', (plan.family_id, plan.limit_bps))


def get_family(db: Connection, family_id: str) -> FamilyPlan | None:
    row = db.execute('SELECT family_id, limit_bps FROM families WHERE family_id = ?',
                     (family_id,)).fetchone()
    return FamilyPlan(*row) if row is not None else None
