from dataclasses import asdict, dataclass
from sqlite3 import Connection

from analysis.binomial import is_significant
from analysis.drafts import ReportDraft
from archive.codec import encode_report_payload
from batches.readback import get_sealed_batch
from desk.budget import family_balance, fits_balance
from desk.commitments import PublicationCommitment, get_commitment, reserve_commitment
from registry.families import require_id
from registry.lookup import read_family, read_registration


@dataclass(frozen=True)
class PublicationClaim:
    request_id: str
    draft: ReportDraft
    limit_bps: int

    def identity(self) -> PublicationCommitment:
        draft = self.draft
        return PublicationCommitment(
            draft.test_id, self.request_id, draft.family_id, draft.alpha_bps,
            encode_report_payload(asdict(draft)),
        )


def check_draft(preparation: Connection, draft: ReportDraft) -> int:
    """Return the frozen family limit after checking one persisted draft."""
    protocol = read_registration(preparation, draft.test_id)
    if (protocol.family_id, protocol.null_rate, protocol.alpha_bps) != (
        draft.family_id, draft.null_rate, draft.alpha_bps,
    ):
        raise ValueError('draft does not match the registered protocol')
    batch = get_sealed_batch(preparation, draft.batch_id, draft.revision)
    if (draft.total, draft.successes) != (len(batch.trials), sum(trial.passed for trial in batch.trials)):
        raise ValueError('draft counts do not match the frozen batch')
    if draft.significant is not is_significant(draft.p_value, protocol.alpha_bps):
        raise ValueError('draft conclusion does not match its probability and registered alpha')
    family = read_family(preparation, protocol.family_id)
    return family.limit_bps


def resolve_claim(preparation: Connection, request_id: str, draft: ReportDraft) -> PublicationClaim:
    require_id(request_id, 'request ID')
    return PublicationClaim(request_id, draft, check_draft(preparation, draft))


def admit_publication(db: Connection, claim: PublicationClaim) -> PublicationCommitment | None:
    identity = claim.identity()
    with db:
        db.execute('BEGIN IMMEDIATE')
        existing = get_commitment(db, identity)
        if existing is not None:
            return existing
        balance = family_balance(db, identity.family_id, claim.limit_bps)
        if not fits_balance(balance, identity.alpha_bps):
            return None
        return reserve_commitment(db, identity)
