from fractions import Fraction

from analysis.workbench import initialize_workspace
from batches.revisions import initialize_batches
from registry.lookup import read_family
from registry.registration import initialize_registry, register
from tests.support import FULL, WorkspaceTest


class RegistryTests(WorkspaceTest):
    def test_fixed_registration(self):
        with self.open() as work:
            original = work.register('coat', 500, 'A', Fraction(1, 2), 300)
            with self.assertRaisesRegex(ValueError, 'conflicting registration'):
                work.register('coat', 500, 'A', Fraction(1, 2), 200)
            with self.assertRaisesRegex(ValueError, 'conflicting family limit'):
                work.register('coat', 400, 'new', Fraction(1, 2), 200)
            with self.assertRaisesRegex(ValueError, 'conflicting registration'):
                work.register('other', 400, 'A', Fraction(1, 2), 300)
            self.assertEqual(work.registration('A'), original)
            with self.assertRaises(KeyError):
                work.registration('new')
            with self.assertRaises(KeyError):
                work.audit('other')
            self.assertEqual(read_family(work.preparation, 'coat').limit_bps, 500)

    def test_identical_registration(self):
        probability = Fraction(2**71 + 3, 2**72 + 9)
        with self.open() as work:
            original = work.register('coat', 500, 'A', probability, 300)
            self.assertEqual(work.register('coat', 500, 'A', probability, 300), original)
            second = work.register('coat', 500, 'B', 0, 300)
            self.assertEqual(second.null_rate, Fraction(0))
            for family, limit, test, rate, alpha in (
                ('bad', -1, 'T', 0, 1), ('bad', 10001, 'T', 0, 1), ('bad', 10, 'T', 0.5, 1),
                ('bad', 10, 'T', Fraction(3, 2), 1), ('bad', 10, 'T', 0, 0),
                ('bad', 10, 'T', 0, True), ('bad', 10, '', 0, 1),
            ):
                with self.subTest(test=test, limit=limit, rate=rate, alpha=alpha):
                    with self.assertRaises(ValueError):
                        work.register(family, limit, test, rate, alpha)
            with self.assertRaises(KeyError):
                work.audit('bad')
        with self.open() as work:
            self.assertEqual(work.registration('A'), original)

    def test_reinitialize_preserves_workspace(self):
        import sqlite3
        from contextlib import closing

        # Begin with only the preparation store and a legitimate user registration.
        with closing(sqlite3.connect(self.path / 'preparation.sqlite3')) as preparation:
            initialize_registry(preparation)
            initialize_batches(preparation)
            protocol = register(preparation, 'custom', 400, 'wear', 1, 250)
        initialize_workspace(self.path)
        with self.open() as work:
            self.assertEqual(work.registration('wear'), protocol)
            batch = work.seal('custom-batch', FULL)
            work.request('original', 'wear', batch.batch_id, batch.revision)
            outcome = work.publish('original')
            original = work.read(outcome.report_id)
            corrected = work.seal('custom-batch', (('01', False), *FULL[1:]))
        initialize_workspace(self.path)
        initialize_workspace(self.path)
        with self.open() as work:
            self.assertEqual(work.registration('wear'), protocol)
            self.assertEqual(work.batch(batch.batch_id, batch.revision), batch)
            self.assertEqual(work.seal(corrected.batch_id, corrected.trials), corrected)
            self.assertEqual(work.status('original'), outcome)
            self.assertEqual(work.read(outcome.report_id), original)
            self.assertEqual(work.audit('custom').published_bps, 250)
