from dataclasses import dataclass
from sqlite3 import Connection

from batches.intake import TrialResult


@dataclass(frozen=True)
class BatchRevision:
    batch_id: str
    revision: int


def initialize_batches(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS batch_revisions (
            batch_id TEXT NOT NULL,
            revision INTEGER NOT NULL CHECK (revision > 0),
            PRIMARY KEY (batch_id, revision)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS batch_trials (
            batch_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            trial_id TEXT NOT NULL,
            passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
            PRIMARY KEY (batch_id, revision, trial_id),
            FOREIGN KEY (batch_id, revision) REFERENCES batch_revisions(batch_id, revision)
        )
    ''')


def find_current_revision(db: Connection, batch_id: str) -> BatchRevision | None:
    row = db.execute('''
        SELECT batch_id, revision FROM batch_revisions
        WHERE batch_id = ? ORDER BY revision DESC LIMIT 1
    ''', (batch_id,)).fetchone()
    return BatchRevision(*row) if row is not None else None


def append_revision(db: Connection, batch_id: str, previous: BatchRevision | None,
                    trials: tuple[TrialResult, ...]) -> BatchRevision:
    revision = 1 if previous is None else previous.revision + 1
    db.execute('INSERT INTO batch_revisions VALUES (?, ?)', (batch_id, revision))
    db.executemany('INSERT INTO batch_trials VALUES (?, ?, ?, ?)', (
        (batch_id, revision, trial.trial_id, int(trial.passed)) for trial in trials
    ))
    return BatchRevision(batch_id, revision)


def load_revision(db: Connection, ref: BatchRevision) -> tuple[TrialResult, ...] | None:
    rows = db.execute('''
        SELECT trial_id, passed FROM batch_trials
        WHERE batch_id = ? AND revision = ? ORDER BY trial_id COLLATE BINARY
    ''', (ref.batch_id, ref.revision)).fetchall()
    if not rows:
        return None
    return tuple(TrialResult(trial_id, bool(passed)) for trial_id, passed in rows)
