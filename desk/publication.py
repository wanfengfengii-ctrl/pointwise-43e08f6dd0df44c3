from sqlite3 import Connection

from analysis.drafts import ReportDraft
from archive.receipts import PublicationReceipt, add_receipt
from archive.records import ReportRecord, insert_report
from desk.commitments import get_commitment, record_publication
from desk.intake import PublicationClaim, admit_publication, resolve_claim
from desk.settlement import PublicationEvent, PublicationOutcome, lookup_outcome, outcome_for


def publish(db: Connection, preparation: Connection, request_id: str, draft: ReportDraft,
            event: PublicationEvent | None = None) -> PublicationOutcome:
    claim = resolve_claim(preparation, request_id, draft)
    if event is not None:
        event('before_admission')
    admitted = admit_publication(db, claim)
    if admitted is None:
        return PublicationOutcome(request_id, draft.test_id, 'insufficient')
    if admitted.status != 'reserved':
        return lookup_outcome(db, claim)
    if event is not None:
        event('after_admission')
    return complete_publication(db, claim, event)


def complete_publication(db: Connection, claim: PublicationClaim,
                         event: PublicationEvent | None = None) -> PublicationOutcome:
    identity = claim.identity()
    with db:
        db.execute('BEGIN IMMEDIATE')
        current = get_commitment(db, identity)
        if current is None:
            raise ValueError('publication requires an admitted application')
        if current.status != 'reserved':
            return outcome_for(db, claim, current)

        report_id = 'R-' + claim.request_id
        insert_report(db, ReportRecord(report_id, claim.request_id, claim.draft))
        add_receipt(db, PublicationReceipt(report_id, claim.request_id))
        record_publication(db, current)
        if event is not None:
            event('before_commit')
    if event is not None:
        event('after_commit')
    return PublicationOutcome(claim.request_id, claim.draft.test_id, 'published', report_id)
