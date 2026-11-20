from tests.support import WorkspaceTest, lose_at, scenario


class BudgetTests(WorkspaceTest):
    def test_shared_family_limit(self):
        with self.open() as work:
            self.prepare_family(work)
            outcomes = [self.issue(work, name) for name in ('A', 'B', 'C')]
            states = [result.status for result in outcomes]
            self.assertEqual(states, ['published', 'insufficient', 'published'])
            self.assertIsNone(outcomes[1].report_id)
            self.assert_no_report(work, 'b')
            issued = [work.read(outcomes[index].report_id) for index in (0, 2)]
            charges = [result.record.draft.alpha_bps for result in issued]
            self.assertEqual(charges, [300, 200])
            audit = self.assert_audit(work, 500, 0, 0)
            scenario('v5', {'limit_bps': 500, 'charges_bps': [300, 300, 200]},
                     ['published', 'insufficient', 'published'], states,
                     {'report_charges_bps': [300, 200], 'available_bps': 0},
                     {'report_charges_bps': charges, 'available_bps': audit.available_bps},
                     ['desk/intake.py', 'desk/budget.py', 'desk/publication.py', 'archive/readback.py'],
                     '300 fits first, the other 300 exceeds the remaining 200, and the final 200 fits.')

            work.register('zero', 0, 'Z', 1, 1)
            work.request('z', 'Z', 'six', 1)
            self.assertEqual(work.publish('z').status, 'insufficient')
            self.assert_no_report(work, 'z')
            self.assertEqual(work.audit('zero').available_bps, 0)
            work.register('separate', 300, 'S', 1, 300)
            work.request('s', 'S', 'six', 1)
            self.assertEqual(work.publish('s').status, 'published')
            self.assertEqual(work.audit('separate').published_bps, 300)
            self.assert_audit(work, 500, 0, 0)

    def test_pending_capacity(self):
        with self.open() as work:
            self.prepare_family(work)
            self.apply(work, 'A')
            self.assertEqual(work.publish('a', lose_at('after_admission')).status, 'pending')
            self.assert_no_report(work, 'a')
            self.assert_audit(work, 0, 300, 200)
            self.assertEqual(self.issue(work, 'B').status, 'insufficient')
            self.assert_no_report(work, 'b')
            self.assertEqual(self.issue(work, 'C').status, 'published')
            self.assert_audit(work, 200, 300, 0)
            self.assertEqual(work.publish('a').status, 'published')
            self.assert_audit(work, 500, 0, 0)
