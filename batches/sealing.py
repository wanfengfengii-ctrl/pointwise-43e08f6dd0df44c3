from collections.abc import Iterable
from sqlite3 import Connection

from batches.intake import TrialResult, parse_submission
from batches.readback import SealedBatch
from batches.revisions import append_revision, find_current_revision, load_revision
from batches.validation import validate_trials


def seal(db: Connection, batch_id: str,
         rows: Iterable[TrialResult | tuple[str, bool]]) -> SealedBatch:
    trials = validate_trials(parse_submission(batch_id, rows))
    with db:
        db.execute('BEGIN IMMEDIATE')
        current = find_current_revision(db, batch_id)
        if current is not None and load_revision(db, current) == trials:
            return SealedBatch(batch_id, current.revision, trials)
        new = append_revision(db, batch_id, current, trials)
        return SealedBatch(batch_id, new.revision, trials)
