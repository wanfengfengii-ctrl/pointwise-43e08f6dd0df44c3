from batches.intake import BatchSubmission, TrialResult


def validate_trials(submission: BatchSubmission) -> tuple[TrialResult, ...]:
    if not isinstance(submission.batch_id, str) or not submission.batch_id.strip():
        raise ValueError('batch ID must be a nonblank string')
    if not submission.trials:
        raise ValueError('at least one trial is required')

    trial_ids = set()
    for trial in submission.trials:
        if not isinstance(trial.trial_id, str) or not trial.trial_id.strip():
            raise ValueError('trial ID must be a nonblank string')
        if type(trial.passed) is not bool:
            raise ValueError(f'trial {trial.trial_id!r} needs a Boolean result')
        if trial.trial_id in trial_ids:
            raise ValueError(f'duplicate trial ID {trial.trial_id!r}')
        trial_ids.add(trial.trial_id)
    return tuple(sorted(submission.trials, key=lambda trial: trial.trial_id))
