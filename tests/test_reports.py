from fractions import Fraction

from tests.support import CORRECTED, WorkspaceTest, scenario


class ReportTests(WorkspaceTest):
    def test_exact_tail(self):
        with self.open() as work:
            self.prepare_family(work)
            application = self.apply(work, 'A')
            self.assert_no_report(work, 'a')
            self.assertEqual(application.draft.p_value, Fraction(1, 64))
            published = work.publish('a')
            result = work.read(published.report_id)
            draft = result.record.draft
            self.assertEqual((draft.p_value, draft.alpha_bps, draft.significant), (Fraction(1, 64), 300, True))
            self.assertEqual((draft.null_rate, draft.total, draft.successes), (Fraction(1, 2), 6, 6))
            self.assertEqual((result.parent.batch_id, result.parent.revision), ('six', 1))
            self.assertEqual(result.receipt.request_id, 'a')
            audit = self.assert_audit(work, 300, 0, 200)
            scenario('v3', {'n': 6, 'k': 6, 'p0': [1, 2], 'alpha_bps': 300},
                     {'p': [1, 64], 'significant': True},
                     {'p': [draft.p_value.numerator, draft.p_value.denominator], 'significant': draft.significant},
                     {'published_bps': 300, 'parent': ['six', 1]},
                     {'published_bps': audit.published_bps, 'parent': [result.parent.batch_id, result.parent.revision]},
                     ['analysis/binomial.py', 'analysis/drafts.py', 'desk/publication.py', 'archive/readback.py'],
                     'One of the 64 equiprobable sequences has six successes. 1/64 is below 3%.')

    def test_nonsignificant_uses_budget(self):
        with self.open() as work:
            self.prepare_family(work)
            result = work.read(self.issue(work, 'C').report_id)
            draft = result.record.draft
            self.assertEqual((draft.p_value, draft.significant, draft.alpha_bps), (Fraction(3, 16), False, 200))
            audit = self.assert_audit(work, 200, 0, 300)
            scenario('v4', {'n': 5, 'k': 4, 'p0': [1, 2], 'alpha_bps': 200},
                     {'p': [3, 16], 'significant': False},
                     {'p': [draft.p_value.numerator, draft.p_value.denominator], 'significant': draft.significant},
                     {'published_bps': 200}, {'published_bps': audit.published_bps},
                     ['analysis/binomial.py', 'desk/intake.py', 'archive/family_audit.py'],
                     'Five sequences have four successes and one has five, for 6/32. The fixed charge is 200.')

    def test_alpha_boundary(self):
        with self.open() as work:
            work.register('edges', 2500, 'T', Fraction(1, 2), 2500)
            batch = work.seal('two', [('x', True), ('y', True)])
            work.request('equal', 'T', 'two', batch.revision)
            record = work.read(work.publish('equal').report_id).record
            self.assertEqual(record.draft.p_value, Fraction(1, 4))
            self.assertTrue(record.draft.significant)
            self.assertEqual(work.audit('edges').available_bps, 0)

    def test_tail_edges(self):
        with self.open() as work:
            for name, null, count, expected in (
                ('zero-of-zero', 0, 0, 1), ('positive-at-zero', 0, 1, 0),
                ('all-at-one', 1, 3, 1), ('zero-at-half', Fraction(1, 2), 0, 1),
            ):
                with self.subTest(name=name):
                    work.register('edges', 1000, name, null, 100)
                    batch = work.seal(name, [(str(i), i < count) for i in range(3)])
                    work.request(name, name, name, batch.revision)
                    draft = work.read(work.publish(name).report_id).record.draft
                    self.assertEqual(draft.p_value, Fraction(expected))
                    self.assertEqual(draft.significant, expected == 0)
            self.assertEqual(work.audit('edges').published_bps, 400)

    def test_original_request_conflict(self):
        with self.open() as work:
            self.prepare_family(work)
            for test_id, batch_id, revision in (('missing', 'six', 1), ('A', 'six', 2), ('A', 'missing', 1)):
                with self.subTest(test_id=test_id, batch_id=batch_id, revision=revision):
                    with self.assertRaises(KeyError):
                        work.request('a', test_id, batch_id, revision)
            first = self.issue(work, 'A')
            second_revision = work.seal('six', CORRECTED)
            self.assertEqual(work.request('a', 'A', 'six', 1).outcome, first)
            with self.assertRaisesRegex(ValueError, 'conflicting parameters'):
                work.request('a', 'A', 'six', second_revision.revision)
            with self.assertRaisesRegex(ValueError, 'conflicting parameters'):
                work.request('a', 'B', 'six', 1)
            with self.assertRaisesRegex(ValueError, 'already belongs to request'):
                work.request('different', 'A', 'six', 1)
            self.assertEqual(work.read(first.report_id).parent.revision, 1)
            self.assertEqual(work.publish('a'), first)
            self.assert_audit(work, 300, 0, 200)
