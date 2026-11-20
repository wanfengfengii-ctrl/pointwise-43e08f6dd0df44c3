from fractions import Fraction

from batches.intake import TrialResult
from tests.support import CORRECTED, FULL, WorkspaceTest, scenario


class ArchiveTests(WorkspaceTest):
    def test_fixed_report_after_correction(self):
        with self.open() as work:
            self.prepare_family(work)
            issued = self.issue(work, 'A')
            first = work.read(issued.report_id)
            self.assertEqual(work.seal('six', CORRECTED).revision, 2)
        with self.open() as work:
            recovered = work.read(issued.report_id)
            self.assertEqual(recovered, first)
            self.assertEqual(recovered.record.report_id, 'R-a')
            self.assertEqual(recovered.record.draft.p_value, Fraction(1, 64))
            self.assertTrue(recovered.record.draft.significant)
            self.assertEqual(recovered.parent.revision, 1)
            self.assertEqual(work.publish('a'), issued)
            self.assert_audit(work, 300, 0, 200)

    def test_exact_parent_contents(self):
        with self.open() as work:
            self.prepare_family(work)
            a = self.issue(work, 'A')
            corrected = work.seal('six', CORRECTED)
            work.cancel('a')
            work.register('other', 300, 'next', Fraction(1, 2), 300)
            work.request('next', 'next', 'six', corrected.revision)
            other = work.publish('next')
        with self.open() as work:
            old = work.read(a.report_id)
            new = work.read(other.report_id)
            self.assertEqual(old.parent.trials, tuple(TrialResult(*row) for row in FULL))
            self.assertEqual(new.parent.trials, tuple(TrialResult(*row) for row in CORRECTED))
            self.assertEqual(new.parent.revision, 2)
            probabilities = [item.record.draft.p_value for item in (old, new)]
            self.assertEqual(probabilities, [Fraction(1, 64), Fraction(7, 64)])
            self.assertEqual((old.record.draft.significant, new.record.draft.significant), (True, False))
            counts = [sum(trial.passed for trial in item.parent.trials) for item in (old, new)]
            self.assertEqual(counts, [6, 5])
            scenario('v8.exact_parent_contents', {'batch': 'six', 'corrected_trial': '01', 'reports': ['R-a', 'R-next']},
                     {'parent_revisions': [1, 2], 'successes': [6, 5]},
                     {'parent_revisions': [old.parent.revision, new.parent.revision], 'successes': counts},
                     {'p': [[1, 64], [7, 64]]},
                     {'p': [[probability.numerator, probability.denominator] for probability in probabilities]},
                     ['batches/sealing.py', 'batches/readback.py', 'archive/records.py', 'archive/readback.py'],
                     'Six successes have one sequence. At least five successes have seven sequences out of 64.')
