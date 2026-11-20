from fractions import Fraction

from analysis.requests import record_outcome
from archive.receipts import find_application_receipt
from archive.records import load_report
from desk.intake import resolve_claim
from desk.publication import complete_publication, publish
from tests.support import WorkspaceTest, lose_at, scenario


class SettlementTests(WorkspaceTest):
    def test_cancel_before_late_message(self):
        with self.open() as work:
            self.prepare_family(work)
            application = self.apply(work, 'A')
            claim = resolve_claim(work.preparation, application.request_id, application.draft)
            self.assertEqual(work.publish('a', lose_at('after_admission')).status, 'pending')
            self.assert_audit(work, 0, 300, 200)
            cancellation = work.cancel('a')
            self.assertEqual(cancellation.status, 'cancelled')
            self.assert_audit(work, 0, 0, 500)
            b = self.issue(work, 'B')
            c = self.issue(work, 'C')
            self.assertEqual((b.status, c.status), ('published', 'published'))
        with self.open() as work:
            late = complete_publication(work.desk, claim)
            self.assertEqual(late.status, 'cancelled')
            self.assertEqual(work.publish('a'), cancellation)
            self.assert_no_report(work, 'a')
            charges = [work.read(outcome.report_id).record.draft.alpha_bps for outcome in (b, c)]
            self.assertEqual(charges, [300, 200])
            audit = self.assert_audit(work, 500, 0, 0)
            scenario('v6', {'reserved_A_bps': 300, 'order': ['cancel', 'sign B and C', 'late completion']},
                     {'cancel': 'cancelled', 'late': 'cancelled'},
                     {'cancel': cancellation.status, 'late': late.status},
                     {'report_charges_bps': [300, 200], 'published_bps': 500},
                     {'report_charges_bps': charges, 'published_bps': audit.published_bps},
                     ['analysis/cancellation.py', 'desk/settlement.py', 'desk/publication.py', 'archive/readback.py'],
                     'Cancellation releases A before B spends 300. A cannot spend those basis points again.')

    def test_cancel_before_admission(self):
        with self.open() as work:
            self.prepare_family(work)
            with self.assertRaises(KeyError):
                work.cancel('missing')
            application = self.apply(work, 'A')
            self.assertEqual(work.publish('a', lose_at('before_admission')).status, 'pending')
            self.assertEqual(work.status('a').status, 'pending')
            self.assert_audit(work, 0, 0, 500)
            self.assertEqual(work.cancel('a').status, 'cancelled')
        with self.open() as work:
            late = publish(work.desk, work.preparation, application.request_id, application.draft)
            self.assertEqual(late.status, 'cancelled')
            self.assert_no_report(work, 'a')
            self.assertEqual(work.status('a').status, 'cancelled')
            self.assertEqual(self.issue(work, 'B').status, 'published')
            self.assert_audit(work, 300, 0, 200)

    def test_lost_publication_reply(self):
        with self.open() as work:
            self.prepare_family(work)
            self.apply(work, 'A')
            lost = work.publish('a', lose_at('after_commit'))
            self.assertEqual(lost.status, 'pending')
            self.assertIsNone(lost.report_id)
            original = work.read('R-a')
            self.assertEqual(original.record.draft.p_value, Fraction(1, 64))
            self.assert_audit(work, 300, 0, 200)
        with self.open() as work:
            self.assertEqual(work.application('a').outcome, lost)
            cancellation = work.cancel('a')
            self.assertEqual((cancellation.status, cancellation.report_id), ('published', 'R-a'))
            self.assertEqual(work.status('a'), cancellation)
            self.assertEqual(work.request('a', 'A', 'six', 1).outcome, cancellation)
            self.assertEqual(work.publish('a'), cancellation)
            self.assertEqual(work.read(cancellation.report_id), original)
            b = self.issue(work, 'B')
            c = self.issue(work, 'C')
            self.assertEqual((b.status, c.status), ('insufficient', 'published'))
            self.assert_no_report(work, 'b')
            charges = [work.read(item.report_id).record.draft.alpha_bps for item in (cancellation, c)]
            self.assertEqual(charges, [300, 200])
            audit = self.assert_audit(work, 500, 0, 0)
            scenario('v7', {'limit_bps': 500, 'charges_bps': [300, 300, 200], 'lost_phase': 'after_commit'},
                     ['pending', 'published', 'insufficient', 'published'],
                     [lost.status, cancellation.status, b.status, c.status],
                     {'original_report': 'R-a', 'report_charges_bps': [300, 200], 'published_bps': 500},
                     {'original_report': cancellation.report_id, 'report_charges_bps': charges,
                      'published_bps': audit.published_bps},
                     ['analysis/cancellation.py', 'analysis/reconciliation.py', 'desk/publication.py',
                      'desk/settlement.py', 'archive/readback.py'],
                     'After the public commit A must retain 300. B cannot fit in 200. C can.')

    def test_pending_balance(self):
        with self.open() as work:
            self.prepare_family(work)
            self.apply(work, 'A')
            self.assertEqual(work.publish('a', lose_at('after_admission')).status, 'pending')
        with self.open() as work:
            self.assertEqual(work.status('a').status, 'pending')
            self.assertEqual(self.issue(work, 'C').status, 'published')
            self.assert_audit(work, 200, 300, 0)
            self.assert_no_report(work, 'a')
            self.assertEqual(work.publish('a', lose_at('after_commit')).status, 'pending')
        with self.open() as work:
            self.assertEqual(work.status('a').report_id, 'R-a')
            self.assertEqual(work.read('R-c').record.draft.p_value, Fraction(3, 16))
            self.assert_audit(work, 500, 0, 0)

    def test_commit_boundary(self):
        with self.open() as work:
            self.prepare_family(work)
            self.apply(work, 'A')
            before_commit = work.publish('a', lose_at('before_commit'))
            self.assertEqual(before_commit.status, 'pending')
            self.assert_no_report(work, 'a')
            self.assertIsNone(load_report(work.desk, 'R-a'))
            self.assertIsNone(find_application_receipt(work.desk, 'a'))
            self.assert_audit(work, 0, 300, 200)
        with self.open() as work:
            pending = work.status('a')
            self.assertEqual(pending.status, 'pending')
            self.apply(work, 'B')
            self.assertEqual(work.publish('b').status, 'insufficient')
            self.assertEqual(work.cancel('a', lose_at('after_cancel_commit')).status, 'pending')
            self.assert_audit(work, 0, 0, 500)
        with self.open() as work:
            cancelled = work.status('a')
            self.assertEqual(cancelled.status, 'cancelled')
            self.assertEqual(record_outcome(work.analysis, pending), cancelled)
            self.assertEqual(work.publish('a'), cancelled)
            self.assert_no_report(work, 'a')
            self.assertEqual(work.publish('b', lose_at('after_commit')).status, 'pending')
            self.assertEqual(work.read('R-b').receipt.request_id, 'b')
        with self.open() as work:
            recovered = work.publish('b')
            self.assertEqual((recovered.status, recovered.report_id), ('published', 'R-b'))
            self.assertEqual(work.cancel('b'), recovered)
            self.assert_audit(work, 300, 0, 200)
