from collections.abc import Callable
from dataclasses import dataclass
from sqlite3 import Connection

from archive.receipts import find_application_receipt
from desk.commitments import PublicationCommitment, get_commitment, record_cancellation
from desk.grouping import member_owner
from desk.intake import PublicationClaim


class ReplyUnavailable(Exception):
    """The caller did not receive a business decision for this delivery."""


PublicationEvent = Callable[[str], None]


@dataclass(frozen=True)
class PublicationOutcome:
    request_id: str
    test_id: str
    status: str
    report_id: str | None = None


def outcome_for(db: Connection, claim: PublicationClaim,
                entry: PublicationCommitment | None) -> PublicationOutcome:
    request_id, test_id = claim.request_id, claim.draft.test_id
    if entry is None or entry.status == 'reserved':
        return PublicationOutcome(request_id, test_id, 'pending')
    if entry.status == 'cancelled':
        return PublicationOutcome(request_id, test_id, 'cancelled')
    receipt = find_application_receipt(db, request_id)
    if receipt is None:
        raise RuntimeError('published commitment has no receipt')
    return PublicationOutcome(request_id, test_id, 'published', receipt.report_id)


def lookup_outcome(db: Connection, claim: PublicationClaim) -> PublicationOutcome:
    if member_owner(db, claim.draft.test_id) is not None:
        return PublicationOutcome(claim.request_id, claim.draft.test_id, 'pending')
    identity = claim.identity()
    with db:
        db.execute('BEGIN')
        return outcome_for(db, claim, get_commitment(db, identity))


def requires_group_guard(db: Connection, test_id: str) -> bool:
    """True when a group already owns this test at the publication desk."""
    return member_owner(db, test_id) is not None


def settle_cancellation(db: Connection, claim: PublicationClaim,
                        event: PublicationEvent | None = None) -> PublicationOutcome:
    identity = claim.identity()
    if member_owner(db, claim.draft.test_id) is not None:
        raise ValueError(f'test {claim.draft.test_id!r} already belongs to a group publication')
    if event is not None:
        event('before_cancel')
    with db:
        db.execute('BEGIN IMMEDIATE')
        entry = get_commitment(db, identity)
        if entry is not None and entry.status != 'reserved':
            result = outcome_for(db, claim, entry)
        else:
            record_cancellation(db, identity, entry)
            result = PublicationOutcome(claim.request_id, claim.draft.test_id, 'cancelled')
    if event is not None:
        event('after_cancel_commit')
    return result
