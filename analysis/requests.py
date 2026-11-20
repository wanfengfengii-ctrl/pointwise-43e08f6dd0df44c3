from dataclasses import asdict, dataclass
from sqlite3 import Connection

from analysis.drafts import ReportDraft, build_draft
from analysis.reconciliation import ApplicationOutcome
from archive.codec import decode_report_payload, encode_report_payload
from registry.families import require_id


@dataclass(frozen=True)
class Application:
    request_id: str
    draft: ReportDraft
    outcome: ApplicationOutcome


def initialize_applications(db: Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            request_id TEXT PRIMARY KEY NOT NULL,
            test_id TEXT UNIQUE NOT NULL,
            draft_payload TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('pending', 'insufficient', 'published', 'cancelled')),
            report_id TEXT,
            CHECK ((status = 'published') = (report_id IS NOT NULL))
        )
    ''')


def find_application(db: Connection, request_id: str) -> Application | None:
    require_id(request_id, 'request ID')
    row = db.execute('''
        SELECT test_id, draft_payload, status, report_id FROM applications WHERE request_id = ?
    ''', (request_id,)).fetchone()
    if row is None:
        return None
    test_id, payload, status, report_id = row
    return Application(request_id, ReportDraft(**decode_report_payload(payload)),
                       ApplicationOutcome(request_id, test_id, status, report_id))


def require_application(db: Connection, request_id: str) -> Application:
    application = find_application(db, request_id)
    if application is None:
        raise KeyError(f'unknown application {request_id!r}')
    return application


def request(db: Connection, preparation: Connection, request_id: str, test_id: str,
            batch_id: str, revision: int) -> Application:
    require_id(request_id, 'request ID')
    require_id(test_id, 'test ID')
    require_id(batch_id, 'batch ID')
    if type(revision) is not int or revision <= 0:
        raise ValueError('revision must be a positive integer')
    with db:
        db.execute('BEGIN IMMEDIATE')
        original = find_application(db, request_id)
        if original is not None:
            draft = original.draft
            if (draft.test_id, draft.batch_id, draft.revision) != (test_id, batch_id, revision):
                raise ValueError(f'conflicting parameters for request {request_id!r}')
            return original
        existing = db.execute('SELECT request_id FROM applications WHERE test_id = ?',
                              (test_id,)).fetchone()
        if existing is not None:
            raise ValueError(f'test {test_id!r} already belongs to request {existing[0]!r}')

        draft = build_draft(preparation, test_id, batch_id, revision)
        db.execute('''
            INSERT INTO applications (request_id, test_id, draft_payload, status)
            VALUES (?, ?, ?, 'pending')
        ''', (request_id, test_id, encode_report_payload(asdict(draft))))
        return Application(request_id, draft, ApplicationOutcome(request_id, test_id, 'pending'))


def record_outcome(db: Connection, outcome: ApplicationOutcome) -> ApplicationOutcome:
    with db:
        db.execute('BEGIN IMMEDIATE')
        original = require_application(db, outcome.request_id)
        saved = original.outcome
        if saved.test_id != outcome.test_id:
            raise ValueError('outcome belongs to a different registered test')
        if saved.terminal:
            if outcome.terminal and outcome != saved:
                raise ValueError('conflicting terminal outcome')
            return saved
        db.execute('UPDATE applications SET status = ?, report_id = ? WHERE request_id = ?',
                   (outcome.status, outcome.report_id, outcome.request_id))
        return outcome
