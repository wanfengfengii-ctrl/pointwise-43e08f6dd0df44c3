import json
from sqlite3 import Connection

from analysis.drafts import ReportDraft
from archive.receipts import PublicationReceipt, add_receipt
from archive.records import ReportRecord, insert_report
from desk.commitments import get_commitment, record_publication
from desk.grouping import (
    GroupClaim, GroupResult, check_group, group_report_id, lookup_group_result,
    member_owner, require_reserved, reserve_members, resolve_group_claim,
)
from desk.intake import PublicationClaim, admit_publication, resolve_claim
from desk.settlement import PublicationEvent, PublicationOutcome, lookup_outcome, outcome_for


def publish(db: Connection, preparation: Connection, request_id: str, draft: ReportDraft,
            event: PublicationEvent | None = None) -> PublicationOutcome:
    claim = resolve_claim(preparation, request_id, draft)
    if member_owner(db, draft.test_id) is not None:
        raise ValueError(f'test {draft.test_id!r} already belongs to a group publication')
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


def publish_group(db: Connection, preparation: Connection, group_id: str,
                  drafts: tuple[ReportDraft, ...],
                  event: PublicationEvent | None = None) -> GroupResult:
    """Check occupancy and the whole charge, then expose the whole group at once."""
    claim = resolve_group_claim(preparation, group_id, drafts)
    saved = lookup_group_result(db, group_id)
    if saved is not None and saved.status == 'published':
        return saved
    with db:
        db.execute('BEGIN IMMEDIATE')
        refusal = check_group(db, claim)
        if refusal is not None:
            return refusal
        reserve_members(db, claim)
        result = finish_group(db, claim)
        if event is not None:
            event('before_commit')
    if event is not None:
        event('after_commit')
    return result


def hold_group(db: Connection, preparation: Connection, group_id: str,
               drafts: tuple[ReportDraft, ...],
               event: PublicationEvent | None = None) -> GroupResult:
    """Persist a complete group reservation without exposing any member report."""
    claim = resolve_group_claim(preparation, group_id, drafts)
    saved = lookup_group_result(db, group_id)
    if saved is not None and saved.status == 'published':
        return saved
    with db:
        db.execute('BEGIN IMMEDIATE')
        refusal = check_group(db, claim)
        if refusal is not None:
            return refusal
        reserve_members(db, claim)
    return GroupResult(group_id, 'pending')


def finish_group(db: Connection, claim: GroupClaim) -> GroupResult:
    """Write every member body, receipt and the group result in the caller's transaction."""
    saved = lookup_group_result(db, claim.group_id)
    if saved is not None and saved.status == 'published':
        return saved
    require_reserved(db, claim)
    report_ids = []
    for member in claim.members:
        current = get_commitment(db, member.claim.identity())
        report_id = group_report_id(claim.group_id, member.test_id)
        insert_report(db, ReportRecord(report_id, member.request_id, member.claim.draft))
        add_receipt(db, PublicationReceipt(report_id, member.request_id))
        record_publication(db, current)
        report_ids.append(report_id)
    result = GroupResult(claim.group_id, 'published', tuple(report_ids))
    db.execute('UPDATE group_publications SET status = ?, report_ids = ? WHERE group_id = ?',
               ('published', json.dumps(list(report_ids)), claim.group_id))
    return result


def group_status(db: Connection, group_id: str) -> GroupResult:
    saved = lookup_group_result(db, group_id)
    return saved if saved is not None else GroupResult(group_id, 'pending')
