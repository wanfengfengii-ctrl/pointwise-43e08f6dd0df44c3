from batches.intake import TrialResult
from tests.support import CORRECTED, FULL, WorkspaceTest


class BatchTests(WorkspaceTest):
    def test_conflicting_trial(self):
        with self.open() as work:
            original = work.seal('base', FULL)
            for batch_id in ('base', 'new'):
                with self.subTest(batch_id=batch_id):
                    with self.assertRaisesRegex(ValueError, 'duplicate trial ID'):
                        work.seal(batch_id, iter((('01', True), ('01', False))))
            with self.assertRaises(KeyError):
                work.batch('new', 1)
            with self.assertRaises(KeyError):
                work.batch('base', 2)
            self.assertEqual(work.batch('base', 1), original)

    def test_invalid_submission(self):
        with self.open() as work:
            for trials in ([], [('', True)], [(None, False)], [('x', 1)],
                           [('x', 'true')], [('x', True), ('x', True)], [('x',)], None):
                with self.subTest(trials=trials):
                    with self.assertRaises(ValueError):
                        work.seal('invalid', trials)
            with self.assertRaises(ValueError):
                work.seal('  ', [('ok', True)])
            with self.assertRaises(KeyError):
                work.batch('invalid', 1)
            self.assertEqual(work.seal('invalid', [('ok', True)]).revision, 1)

    def test_independent_revision(self):
        with self.open() as work:
            first = work.seal('batch', reversed(FULL))
            self.assertEqual(first.revision, 1)
            self.assertEqual(first.trials, tuple(TrialResult(*row) for row in FULL))
            self.assertEqual(work.seal('batch', FULL), first)
            second = work.seal('batch', CORRECTED)
            self.assertEqual(second.revision, 2)
        with self.open() as work:
            self.assertEqual(work.seal('batch', reversed(CORRECTED)), second)
            self.assertEqual(work.batch('batch', 1), first)
            self.assertEqual(work.batch('batch', 2), second)
            third = work.seal('batch', FULL)
            self.assertEqual(third.revision, 3)
            self.assertEqual(third.trials, first.trials)
