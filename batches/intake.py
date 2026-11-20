from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class TrialResult:
    trial_id: str
    passed: bool


@dataclass(frozen=True)
class BatchSubmission:
    batch_id: str
    trials: tuple[TrialResult, ...]


def parse_submission(batch_id: str, rows: Iterable[TrialResult | tuple[str, bool]]) -> BatchSubmission:
    try:
        records = iter(rows)
    except TypeError as error:
        raise ValueError('trials must be a sequence of trial records') from error

    trials = []
    for row in records:
        if isinstance(row, TrialResult):
            trials.append(row)
        elif isinstance(row, (tuple, list)) and len(row) == 2:
            trials.append(TrialResult(*row))
        else:
            raise ValueError('each trial must contain an ID and a Boolean result')
    return BatchSubmission(batch_id, tuple(trials))
