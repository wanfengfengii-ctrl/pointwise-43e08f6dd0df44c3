from dataclasses import dataclass
from sqlite3 import Connection

from batches.intake import TrialResult
from batches.revisions import BatchRevision, load_revision


@dataclass(frozen=True)
class SealedBatch:
    batch_id: str
    revision: int
    trials: tuple[TrialResult, ...]


def get_sealed_batch(db: Connection, batch_id: str, revision: int) -> SealedBatch:
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise ValueError('batch ID must be a nonblank string')
    if type(revision) is not int or revision <= 0:
        raise ValueError('revision must be a positive integer')
    trials = None
    if revision < 2**63:
        trials = load_revision(db, BatchRevision(batch_id, revision))
    if trials is None:
        raise KeyError(f'unknown sealed batch {batch_id!r} revision {revision}')
    return SealedBatch(batch_id, revision, trials)
