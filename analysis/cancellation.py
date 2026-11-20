from sqlite3 import Connection

from analysis.reconciliation import ApplicationOutcome, project_outcome
from analysis.requests import record_outcome, require_application
from desk.intake import resolve_claim
from desk.settlement import PublicationEvent, ReplyUnavailable, settle_cancellation


def cancel(db: Connection, preparation: Connection, desk: Connection, request_id: str,
           event: PublicationEvent | None = None) -> ApplicationOutcome:
    original = require_application(db, request_id)
    claim = resolve_claim(preparation, original.request_id, original.draft)
    try:
        reply = settle_cancellation(desk, claim, event)
    except ReplyUnavailable:
        outcome = ApplicationOutcome(request_id, original.draft.test_id, 'pending')
    else:
        outcome = project_outcome(reply)
    return record_outcome(db, outcome)
