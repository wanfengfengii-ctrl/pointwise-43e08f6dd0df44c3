import json
import unittest
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.workbench import Workspace
from desk.settlement import ReplyUnavailable


FULL = tuple((f'{index:02}', True) for index in range(1, 7))
FOUR_OF_FIVE = tuple((f'{index:02}', index != 5) for index in range(1, 6))
CORRECTED = (('01', False), *FULL[1:])


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)

    def open(self):
        return Workspace(self.path)

    def prepare_family(self, work):
        for test_id, alpha in (('A', 300), ('B', 300), ('C', 200)):
            work.register('coat', 500, test_id, Fraction(1, 2), alpha)
        work.seal('six', FULL)
        work.seal('five', FOUR_OF_FIVE)

    def apply(self, work, test_id):
        batch = 'five' if test_id == 'C' else 'six'
        return work.request(test_id.lower(), test_id, batch, 1)

    def issue(self, work, test_id):
        application = self.apply(work, test_id)
        return work.publish(application.request_id)

    def assert_audit(self, work, published, reserved, available):
        audit = work.audit('coat')
        self.assertEqual(audit.limit_bps, 500)
        self.assertEqual((audit.published_bps, audit.reserved_bps, audit.available_bps),
                         (published, reserved, available))
        return audit

    def assert_no_report(self, work, request_id):
        with self.assertRaises(KeyError):
            work.read('R-' + request_id)


def lose_at(wanted):
    def interrupt(phase):
        if phase == wanted:
            raise ReplyUnavailable(phase)
    return interrupt


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
             code_paths, oracle):
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id,
        'input': inputs,
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': code_paths,
        'oracle': oracle,
    }, sort_keys=True))
