from dataclasses import dataclass, replace
from sqlite3 import Connection


@dataclass(frozen=True)
class PublicationCommitment:
    test_id: str
    request_id: str
    family_id: str
    alpha_bps: int
    draft_payload: str
    status: str = 'reserved'


def initialize_commitments(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS publication_commitments (
            test_id TEXT PRIMARY KEY NOT NULL,
            request_id TEXT UNIQUE NOT NULL,
            family_id TEXT NOT NULL,
            alpha_bps INTEGER NOT NULL CHECK (alpha_bps BETWEEN 1 AND 10000),
            draft_payload TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('reserved', 'published', 'cancelled'))
        )
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS commitment_family_status
        ON publication_commitments(family_id, status)
    ''')


def get_commitment(db: Connection, identity: PublicationCommitment) -> PublicationCommitment | None:
    rows = db.execute('''
        SELECT test_id, request_id, family_id, alpha_bps, draft_payload, status
        FROM publication_commitments WHERE test_id = ? OR request_id = ?
    ''', (identity.test_id, identity.request_id)).fetchall()
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError('request and test identify different commitments')
    saved = PublicationCommitment(*rows[0])
    if saved != replace(identity, status=saved.status):
        raise ValueError('conflicting request or frozen draft at the publication desk')
    return saved


def _insert(db: Connection, entry: PublicationCommitment) -> None:
    db.execute('INSERT INTO publication_commitments VALUES (?, ?, ?, ?, ?, ?)', (
        entry.test_id, entry.request_id, entry.family_id, entry.alpha_bps,
        entry.draft_payload, entry.status,
    ))


def reserve_commitment(db: Connection, identity: PublicationCommitment) -> PublicationCommitment:
    reserved = replace(identity, status='reserved')
    _insert(db, reserved)
    return reserved


def _finish_reserved(db: Connection, current: PublicationCommitment, status: str) -> None:
    updated = db.execute('''
        UPDATE publication_commitments SET status = ?
        WHERE test_id = ? AND request_id = ? AND status = 'reserved'
    ''', (status, current.test_id, current.request_id))
    if updated.rowcount != 1:
        raise RuntimeError('publication requires a current reserved commitment')


def record_publication(db: Connection, current: PublicationCommitment) -> None:
    _finish_reserved(db, current, 'published')


def record_cancellation(db: Connection, identity: PublicationCommitment,
                        current: PublicationCommitment | None) -> None:
    if current is None:
        _insert(db, replace(identity, status='cancelled'))
    else:
        _finish_reserved(db, current, 'cancelled')


def sum_family_commitments(db: Connection, family_id: str) -> tuple[int, int]:
    published, reserved = db.execute('''
        SELECT COALESCE(SUM(CASE WHEN status = 'published' THEN alpha_bps ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN status = 'reserved' THEN alpha_bps ELSE 0 END), 0)
        FROM publication_commitments
        WHERE family_id = ? AND status IN ('published', 'reserved')
    ''', (family_id,)).fetchone()
    return published, reserved
