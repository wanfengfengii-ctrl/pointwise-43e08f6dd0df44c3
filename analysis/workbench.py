import argparse
import json
import sqlite3
import sys
from contextlib import ExitStack, closing
from dataclasses import asdict, is_dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.cancellation import cancel
from analysis.groups import GroupOutcome, initialize_groups, record_group_outcome, request_group as freeze_group
from analysis.reconciliation import ApplicationOutcome, project_outcome, resolve_outcome
from analysis.requests import initialize_applications, record_outcome, request, require_application
from archive.codec import rational_parts
from archive.family_audit import audit
from archive.readback import read
from archive.receipts import initialize_receipts
from archive.records import initialize_records
from batches.readback import get_sealed_batch
from batches.revisions import initialize_batches
from batches.sealing import seal
from desk.commitments import initialize_commitments
from desk.grouping import (
    group_report_id,
    initialize_grouping,
    member_request_id as group_member_request_id,
)
from desk.intake import resolve_claim
from desk.publication import (
    group_status as read_group_status,
    hold_group as hold_group_at_desk,
    publish,
    publish_group as publish_group_at_desk,
)
from desk.settlement import ReplyUnavailable
from registry.lookup import read_registration
from registry.registration import initialize_registry, register


class Workspace:
    """Open one local preparation, analysis and publication connection per session."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def __enter__(self):
        self.path.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack:
            self.preparation = self._connect(stack, 'preparation.sqlite3')
            self.analysis = self._connect(stack, 'analysis.sqlite3')
            self.desk = self._connect(stack, 'desk.sqlite3')
            with self.preparation:
                self.preparation.execute('BEGIN IMMEDIATE')
                initialize_registry(self.preparation)
                initialize_batches(self.preparation)
            with self.analysis:
                initialize_applications(self.analysis)
                initialize_groups(self.analysis)
            with self.desk:
                self.desk.execute('BEGIN IMMEDIATE')
                initialize_commitments(self.desk)
                initialize_records(self.desk)
                initialize_receipts(self.desk)
                initialize_grouping(self.desk)
            self._connections = stack.pop_all()
        return self

    def _connect(self, stack: ExitStack, filename: str) -> sqlite3.Connection:
        connection = stack.enter_context(closing(sqlite3.connect(self.path / filename)))
        connection.execute('PRAGMA foreign_keys = ON')
        return connection

    def __exit__(self, *exception):
        return self._connections.__exit__(*exception)

    def register(self, family_id, limit_bps, test_id, null_rate, alpha_bps):
        return register(self.preparation, family_id, limit_bps, test_id, null_rate, alpha_bps)

    def registration(self, test_id):
        return read_registration(self.preparation, test_id)

    def seal(self, batch_id, trials):
        return seal(self.preparation, batch_id, trials)

    def batch(self, batch_id, revision):
        return get_sealed_batch(self.preparation, batch_id, revision)

    def request(self, request_id, test_id, batch_id, revision):
        return request(self.analysis, self.preparation, request_id, test_id, batch_id, revision)

    def application(self, request_id):
        return require_application(self.analysis, request_id)

    def publish(self, request_id, event=None):
        original = self.application(request_id)
        try:
            reply = publish(self.desk, self.preparation, original.request_id, original.draft, event)
        except ReplyUnavailable:
            outcome = ApplicationOutcome(request_id, original.draft.test_id, 'pending')
        else:
            outcome = project_outcome(reply)
        return record_outcome(self.analysis, outcome)

    def status(self, request_id):
        original = self.application(request_id)
        claim = resolve_claim(self.preparation, original.request_id, original.draft)
        outcome = resolve_outcome(self.desk, claim)
        return record_outcome(self.analysis, outcome)

    def cancel(self, request_id, event=None):
        return cancel(self.analysis, self.preparation, self.desk, request_id, event)

    def request_group(self, group_id, members):
        return freeze_group(self.analysis, self.preparation, group_id, members)

    def publish_group(self, group_id, event=None):
        original = self._require_group(group_id)
        try:
            outcome = publish_group_at_desk(self.desk, self.preparation, group_id,
                                            original.drafts, event)
        except ReplyUnavailable:
            outcome = GroupOutcome(group_id, 'pending')
        return record_group_outcome(self.analysis, self._bound_group_outcome(original, outcome))

    def hold_group(self, group_id, event=None):
        original = self._require_group(group_id)
        try:
            outcome = hold_group_at_desk(self.desk, self.preparation, group_id,
                                         original.drafts, event)
        except ReplyUnavailable:
            outcome = GroupOutcome(group_id, 'pending')
        return record_group_outcome(self.analysis, self._bound_group_outcome(original, outcome))

    def group_status(self, group_id):
        original = self._require_group(group_id)
        outcome = read_group_status(self.desk, group_id)
        return record_group_outcome(self.analysis, self._bound_group_outcome(original, outcome))

    def _bound_group_outcome(self, original, outcome):
        """Check that a published group result belongs to the frozen members."""
        if outcome.status != 'published':
            return outcome
        by_test = {draft.test_id: draft for draft in original.drafts}
        if len(outcome.report_ids) != len(by_test) or len(set(outcome.report_ids)) != len(by_test):
            raise RuntimeError('published group does not carry one report per frozen member')
        bound = {}
        for report_id in outcome.report_ids:
            saved = read(self.desk, self.preparation, report_id)
            request_id = saved.receipt.request_id
            draft = saved.record.draft
            if draft.test_id not in by_test or by_test[draft.test_id] != draft:
                raise RuntimeError('group report does not match its frozen draft')
            if request_id != group_member_request_id(original.group_id, draft.test_id):
                raise RuntimeError('group report was not issued for its frozen member')
            bound[draft.test_id] = report_id
        if set(bound) != set(by_test):
            raise RuntimeError('published group omits a frozen member')
        return GroupOutcome(original.group_id, 'published',
                            tuple(bound[test_id] for test_id in sorted(by_test)))

    def _require_group(self, group_id):
        from analysis.groups import require_group
        return require_group(self.analysis, group_id)

    def read(self, report_id):
        return read(self.desk, self.preparation, report_id)

    def audit(self, family_id):
        return audit(self.preparation, self.desk, family_id)


def initialize_workspace(path: str | Path) -> None:
    with Workspace(path):
        pass


def _lose_publication_reply(phase: str) -> None:
    if phase == 'after_commit':
        raise ReplyUnavailable(phase)


def _run_shift(path: Path, sample: dict) -> dict:
    family_id = sample['family_id']
    first, second, third = sample['attempts']
    with Workspace(path) as work:
        for protocol in sample['protocols']:
            work.register(family_id, sample['limit_bps'], protocol['test_id'],
                          Fraction(protocol['null_rate']), protocol['alpha_bps'])
        revisions = {item['batch_id']: work.seal(item['batch_id'], item['trials']).revision
                     for item in sample['batches']}
        work.request(*first, revisions[first[2]])
        lost = work.publish(first[0], _lose_publication_reply)
        before_reopen = work.audit(family_id)

    with Workspace(path) as work:
        cancellation = work.cancel(first[0])
        original = work.publish(first[0])
        work.request(*second, revisions[second[2]])
        refused = work.publish(second[0])
        work.request(*third, revisions[third[2]])
        third_result = work.publish(third[0])
        correction = sample['correction']
        corrected = work.seal(correction['batch_id'], correction['trials'])

    with Workspace(path) as work:
        return {
            'after_lost_reply': lost,
            'audit_after_lost_reply': before_reopen,
            'cancellation_reply': cancellation,
            'second_request': refused,
            'corrected_revision': corrected,
            'reports': [work.read(original.report_id), work.read(third_result.report_id)],
            'final_audit': work.audit(family_id),
        }


def _prepare_sample(work: Workspace, sample: dict) -> None:
    for protocol in sample['protocols']:
        test_id, rate, alpha = protocol
        work.register(sample['family_id'], sample['limit_bps'], test_id, Fraction(rate), alpha)
    for batch_id, trials in sample['batches'].items():
        work.seal(batch_id, trials)


def _read_group(work: Workspace, outcome) -> list[dict]:
    rows = []
    for report_id in outcome.report_ids:
        saved = work.read(report_id)
        draft = saved.record.draft
        rows.append({
            'report_id': report_id,
            'test_id': draft.test_id,
            'batch_id': saved.parent.batch_id,
            'revision': saved.parent.revision,
            'p_value': rational_parts(draft.p_value),
            'significant': draft.significant,
            'alpha_bps': draft.alpha_bps,
        })
    return rows


def _run_group_shift(path: Path, sample: dict) -> dict:
    """Demonstrate overlapping groups that compete for one 500 bps family."""
    family_id = sample['family_id']
    groups = sample['groups']
    correction = sample['correction']
    with Workspace(path) as work:
        _prepare_sample(work, sample)
        frozen = work.request_group('ab', groups['ab'])
        work.request_group('bc', groups['bc'])
        work.request_group('cd', groups['cd'])
        # Reverse order of the same members and revisions freezes to the same request.
        replay = work.request_group('ab', list(reversed(groups['ab'])))
        ab = work.publish_group('ab')
        audit_after_ab = work.audit(family_id)
        bc = work.publish_group('bc')
        audit_after_bc = work.audit(family_id)
        cd = work.publish_group('cd')
        ab_members = _read_group(work, ab)
        try:
            work.read(group_report_id('bc', 'C'))
            c_claimable = True
        except KeyError:
            c_claimable = False

    resume_path = Path(path) / 'resume-demo'
    with Workspace(resume_path) as work:
        _prepare_sample(work, sample)
        work.request_group('resume', groups['ab'])
        work.hold_group('resume')
        held = work.audit(family_id)
        interrupted = work.publish_group('resume', _lose_publication_reply)
        after_interrupt = work.audit(family_id)
        work.seal(correction['batch_id'], correction['trials'])

    with Workspace(resume_path) as work:
        status = work.group_status('resume')
        reread = work.publish_group('resume')
        resumed = _read_group(work, reread)
        return {
            'frozen': {
                'ab': [(draft.test_id, draft.batch_id, draft.revision) for draft in frozen.drafts],
                'reverse_resend_same': replay == frozen,
            },
            'ab': {'status': ab.status, 'report_ids': ab.report_ids, 'members': ab_members},
            'audit_after_ab': audit_after_ab,
            'bc': {'status': bc.status, 'report_ids': bc.report_ids, 'c_report_claimable': c_claimable},
            'audit_after_bc': audit_after_bc,
            'cd': {'status': cd.status, 'report_ids': cd.report_ids},
            'held_reservation': held,
            'lost_after_commit': interrupted,
            'audit_after_interrupt': after_interrupt,
            'group_status_after_reopen': status,
            'resumed_members': resumed,
            'final_audit': work.audit(family_id),
        }


def _as_json(value):
    if isinstance(value, Fraction):
        return rational_parts(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f'cannot encode {type(value).__name__}')


def _parse_fraction(text: str) -> Fraction:
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError) as error:
        raise argparse.ArgumentTypeError('expected an exact rational such as 1/2') from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Offline material-test reporting')
    parser.add_argument('--workspace', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')

    registration = commands.add_parser('register')
    registration.add_argument('family_id')
    registration.add_argument('limit_bps', type=int)
    registration.add_argument('test_id')
    registration.add_argument('null_rate', type=_parse_fraction)
    registration.add_argument('alpha_bps', type=int)

    sealing = commands.add_parser('seal')
    sealing.add_argument('batch_id')
    sealing.add_argument('trials', type=json.loads)

    application = commands.add_parser('request')
    application.add_argument('request_id')
    application.add_argument('test_id')
    application.add_argument('batch_id')
    application.add_argument('revision', type=int)

    for name in ('publish', 'status', 'cancel'):
        commands.add_parser(name).add_argument('request_id')
    commands.add_parser('read').add_argument('report_id')
    commands.add_parser('audit').add_argument('family_id')
    commands.add_parser('demo').add_argument('sample', type=Path, nargs='+')
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command != 'demo' and args.workspace is None:
        parser.error('--workspace is required for workspace commands')
    try:
        if args.command == 'demo':
            result = {}
            for sample_path in args.sample:
                sample = json.loads(sample_path.read_text(encoding='utf-8'))
                runner = _run_group_shift if 'groups' in sample else _run_shift
                with TemporaryDirectory(prefix='material-shift-', dir=args.workspace) as folder:
                    result[sample_path.name] = runner(Path(folder), sample)
            if len(args.sample) == 1:
                result = result[args.sample[0].name]
        elif args.command == 'init':
            initialize_workspace(args.workspace)
            result = {'workspace': str(args.workspace)}
        else:
            arguments = vars(args).copy()
            arguments.pop('workspace')
            arguments.pop('command')
            with Workspace(args.workspace) as work:
                result = getattr(work, args.command)(**arguments)
    except (KeyError, ValueError, OSError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, default=_as_json, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
