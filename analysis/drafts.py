from dataclasses import dataclass
from fractions import Fraction
from sqlite3 import Connection

from analysis.binomial import exact_upper_tail, is_significant
from batches.readback import get_sealed_batch
from registry.lookup import read_registration


@dataclass(frozen=True)
class ReportDraft:
    test_id: str
    family_id: str
    batch_id: str
    revision: int
    null_rate: Fraction
    alpha_bps: int
    total: int
    successes: int
    p_value: Fraction
    significant: bool


def build_draft(db: Connection, test_id: str, batch_id: str, revision: int) -> ReportDraft:
    protocol = read_registration(db, test_id)
    batch = get_sealed_batch(db, batch_id, revision)
    total = len(batch.trials)
    successes = sum(trial.passed for trial in batch.trials)
    p_value = exact_upper_tail(total, successes, protocol.null_rate)
    return ReportDraft(
        protocol.test_id, protocol.family_id, batch.batch_id, batch.revision,
        protocol.null_rate, protocol.alpha_bps, total, successes, p_value,
        is_significant(p_value, protocol.alpha_bps),
    )
