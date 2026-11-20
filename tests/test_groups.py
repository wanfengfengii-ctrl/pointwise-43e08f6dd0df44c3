from fractions import Fraction

from tests.support import FULL, FOUR_OF_FIVE, WorkspaceTest, lose_at, scenario

SEVEN = FULL + (('07', True),)


class GroupTests(WorkspaceTest):
    def prepare_groups(self, work):
        for test_id, alpha in (('A', 100), ('B', 200), ('C', 100), ('D', 101)):
            work.register('coat', 500, test_id, Fraction(1, 2), alpha)
        work.seal('seven', SEVEN)
        work.seal('five', FOUR_OF_FIVE)
        work.seal('two', [('01', True), ('02', True)])

    def freeze(self, work, group_id, members):
        return work.request_group(group_id, members)

    def test_freeze_is_not_occupancy(self):
        with self.open() as work:
            self.prepare_groups(work)
            first = self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            self.assertEqual(first.group_id, 'ab')
            self.assertEqual(tuple(draft.test_id for draft in first.drafts), ('A', 'B'))
            self.assertEqual(first.drafts[0].p_value, Fraction(1, 128))
            self.assertEqual(first.drafts[1].p_value, Fraction(3, 16))
            again = self.freeze(work, 'ab', [('B', 'five', 1), ('A', 'seven', 1)])
            self.assertEqual(again, first)
            other = self.freeze(work, 'ab-alt', [['A', 'seven', 1], ['C', 'two', 1]])
            self.assertEqual(other.drafts[0].test_id, 'A')
            self.assert_audit(work, 0, 0, 500)
            self.assertEqual(work.group_status('ab').status, 'pending')
            self.assertEqual(work.group_status('ab').report_ids, ())

    def test_freeze_conflicts(self):
        with self.open() as work:
            self.prepare_groups(work)
            for members in ([], [['A', 'seven', 1]], [['A', 'seven', 1], ['A', 'five', 1]],
                            [['A', 'seven', 1], ['A', 'seven', 1]]):
                with self.subTest(members=members):
                    with self.assertRaises(ValueError):
                        work.request_group('bad', members)
            for members in ([['A', 'seven', 0]], [['A', 'seven', True]],
                            [['', 'seven', 1]], [['A', '', 1]], [['A', 'seven', '1']],
                            [['A', 'seven', 1, 2]], 'A'):
                with self.subTest(members=members):
                    with self.assertRaises(ValueError):
                        work.request_group('bad', members)
            with self.assertRaises(KeyError):
                work.request_group('bad', [['A', 'seven', 1], ['Z', 'five', 1]])
            with self.assertRaises(KeyError):
                work.request_group('bad', [['A', 'seven', 2], ['B', 'five', 1]])
            with self.assertRaises(KeyError):
                work.request_group('bad', [['A', 'missing', 1], ['B', 'five', 1]])
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            with self.assertRaisesRegex(ValueError, 'conflicting members'):
                work.request_group('ab', [['A', 'seven', 1], ['C', 'two', 1]])
        with self.open() as work:
            with self.assertRaises(KeyError):
                work.publish_group('missing')
            with self.assertRaises(KeyError):
                work.group_status('missing')

    def test_same_text_in_both_namespaces(self):
        with self.open() as work:
            self.prepare_groups(work)
            work.request('c', 'C', 'two', 1)
            group = self.freeze(work, 'c', [['A', 'seven', 1], ['B', 'five', 1]])
            self.assertEqual(group.group_id, 'c')
            single = work.publish('c')
            outcome = work.publish_group('c')
            self.assertEqual(single.status, 'published')
            self.assertEqual(outcome.status, 'published')
            self.assertEqual(work.read('R-c').record.draft.test_id, 'C')
            self.assertEqual(outcome.report_ids, ('G-1:c:A', 'G-1:c:B'))
            self.assertEqual(work.read(outcome.report_ids[0]).record.draft.test_id, 'A')

    def test_whole_group_publish_and_readback(self):
        with self.open() as work:
            self.prepare_groups(work)
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            result = work.publish_group('ab')
            self.assertEqual((result.group_id, result.status), ('ab', 'published'))
            self.assertEqual(len(result.report_ids), 2)
            drafts = [work.read(report_id) for report_id in result.report_ids]
            self.assertEqual([item.record.draft.test_id for item in drafts], ['A', 'B'])
            self.assertEqual([item.record.draft.p_value for item in drafts],
                             [Fraction(1, 128), Fraction(3, 16)])
            self.assertEqual([item.parent.batch_id for item in drafts], ['seven', 'five'])
            self.assertEqual([item.parent.revision for item in drafts], [1, 1])
            self.assertEqual([item.receipt.request_id for item in drafts], ['\x00group:2:ab:A',
                                                                           '\x00group:2:ab:B'])
            audit = self.assert_audit(work, 300, 0, 200)
            self.assertEqual(work.publish_group('ab'), result)
            self.assertEqual(work.group_status('ab'), result)
            scenario('g1', {'members': [['A', 'seven', 1], ['B', 'five', 1]], 'limit_bps': 500},
                     {'status': 'published', 'charges_bps': [100, 200]},
                     {'status': result.status,
                      'charges_bps': [item.record.draft.alpha_bps for item in drafts]},
                     {'published_bps': 300, 'available_bps': 200},
                     {'published_bps': audit.published_bps, 'available_bps': audit.available_bps},
                     ['analysis/groups.py', 'desk/grouping.py', 'desk/publication.py',
                      'archive/readback.py'],
                     'A and B share one family; the group charges 100 + 200 and leaves 200.')

    def test_bc_refused_after_ab(self):
        with self.open() as work:
            self.prepare_groups(work)
            for group_id, members in (('ab', [['A', 'seven', 1], ['B', 'five', 1]]),
                                      ('bc', [['B', 'five', 1], ['C', 'two', 1]]),
                                      ('cd', [['C', 'two', 1], ['D', 'seven', 1]])):
                self.freeze(work, group_id, members)
            first = work.publish_group('ab')
            self.assertEqual(first.status, 'published')
            refused = work.publish_group('bc')
            self.assertEqual(refused.status, 'conflict')
            self.assertEqual(refused.report_ids, ())
            with self.assertRaises(KeyError):
                work.read('G-2:bc:C')
            with self.assertRaises(KeyError):
                work.read('G-2:bc:B')
            short = work.publish_group('cd')
            self.assertEqual(short.status, 'insufficient')
            self.assertEqual(short.report_ids, ())
            with self.assertRaises(KeyError):
                work.read('G-2:cd:C')
            audit = self.assert_audit(work, 300, 0, 200)
            self.assertEqual(work.group_status('bc').status, 'pending')
            scenario('g2', {'first': 'ab', 'second': 'bc', 'third': 'cd', 'limit_bps': 500},
                     {'ab': 'published', 'bc': 'conflict', 'cd': 'insufficient'},
                     {'ab': first.status, 'bc': refused.status, 'cd': short.status},
                     {'C_extra_reports': 0, 'published_bps': 300, 'available_bps': 200},
                     {'C_extra_reports': 0, 'published_bps': audit.published_bps,
                      'available_bps': audit.available_bps},
                     ['desk/grouping.py', 'desk/budget.py', 'desk/publication.py'],
                     'B is owned by ab, so bc conflicts. cd charges 201 into 200 and is refused.')

    def test_reverse_winner_order(self):
        with self.open() as work:
            self.prepare_groups(work)
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            self.freeze(work, 'bc', [['B', 'five', 1], ['C', 'two', 1]])
            self.assertEqual(work.publish_group('bc').status, 'published')
            refused = work.publish_group('ab')
            self.assertEqual(refused.status, 'conflict')
            with self.assertRaises(KeyError):
                work.read('G-2:ab:A')
            self.assert_audit(work, 300, 0, 200)

    def test_group_holds_test_against_single(self):
        with self.open() as work:
            self.prepare_groups(work)
            work.request('b', 'B', 'five', 1)
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            self.assertEqual(work.publish_group('ab').status, 'published')
            with self.assertRaises(ValueError):
                work.publish('b')
            with self.assertRaises(ValueError):
                work.cancel('b')
            self.assertEqual(work.status('b').status, 'pending')
            with self.assertRaises(KeyError):
                work.read('R-b')
            self.assert_audit(work, 300, 0, 200)

    def test_single_hold_blocks_group(self):
        with self.open() as work:
            self.prepare_groups(work)
            work.request('b', 'B', 'five', 1)
            self.assertEqual(work.publish('b', lose_at('after_admission')).status, 'pending')
            self.assert_audit(work, 0, 200, 300)
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            refused = work.publish_group('ab')
            self.assertEqual(refused.status, 'conflict')
            self.assert_audit(work, 0, 200, 300)
            self.assertEqual(work.cancel('b').status, 'cancelled')
            self.assert_audit(work, 0, 0, 500)
            still = work.publish_group('ab')
            self.assertEqual(still.status, 'conflict')
            with self.assertRaises(KeyError):
                work.read('G-2:ab:A')
            self.assert_audit(work, 0, 0, 500)

    def test_preheld_group_stays_complete(self):
        with self.open() as work:
            self.prepare_groups(work)
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            self.freeze(work, 'bc', [['B', 'five', 1], ['C', 'two', 1]])
            held = work.hold_group('ab')
            self.assertEqual((held.status, held.report_ids), ('pending', ()))
            self.assert_audit(work, 0, 300, 200)
            self.assertEqual(work.publish_group('bc').status, 'conflict')
            self.assert_audit(work, 0, 300, 200)
            with self.assertRaises(KeyError):
                work.read('G-2:ab:A')
            failed = work.publish_group('ab', lose_at('before_commit'))
            self.assertEqual(failed.status, 'pending')
            self.assert_audit(work, 0, 300, 200)
        with self.open() as work:
            self.assertEqual(work.group_status('ab').status, 'pending')
            with self.assertRaises(KeyError):
                work.read('G-2:ab:A')
            result = work.publish_group('ab')
            self.assertEqual(result.status, 'published')
            self.assertEqual(result.report_ids, ('G-2:ab:A', 'G-2:ab:B'))
            self.assert_audit(work, 300, 0, 200)

    def test_before_commit_leaves_nothing_claimable(self):
        with self.open() as work:
            self.prepare_groups(work)
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            self.freeze(work, 'bc', [['B', 'five', 1], ['C', 'two', 1]])
            failed = work.publish_group('ab', lose_at('before_commit'))
            self.assertEqual(failed.status, 'pending')
            for report_id in ('G-2:ab:A', 'G-2:ab:B'):
                with self.assertRaises(KeyError):
                    work.read(report_id)
            audit = self.assert_audit(work, 0, 0, 500)
            self.assertEqual(work.publish_group('bc').status, 'published')
            resumed = work.publish_group('ab')
            self.assertEqual(resumed.status, 'conflict')
            self.assert_audit(work, 300, 0, 200)
            scenario('g3', {'lost_phase': 'before_commit', 'resume': 'ab after bc'},
                     {'first': 'pending', 'resume': 'conflict'},
                     {'first': failed.status, 'resume': resumed.status},
                     {'claimable_members': 0, 'published_bps': 300},
                     {'claimable_members': 0, 'published_bps': audit.published_bps},
                     ['desk/publication.py', 'desk/grouping.py', 'archive/records.py'],
                     'A rolled-back group exposes nothing; capacity is rechecked on resume.')

    def test_after_commit_resume_keeps_original_numbers(self):
        with self.open() as work:
            self.prepare_groups(work)
            self.freeze(work, 'ab', [['A', 'seven', 1], ['B', 'five', 1]])
            lost = work.publish_group('ab', lose_at('after_commit'))
            self.assertEqual((lost.status, lost.report_ids), ('pending', ()))
            self.assert_audit(work, 300, 0, 200)
            for report_id in ('G-2:ab:A', 'G-2:ab:B'):
                self.assertEqual(work.read(report_id).parent.revision, 1)
            corrected = work.seal('seven', (('01', False), *FULL[1:]))
            self.assertEqual(corrected.revision, 2)
        with self.open() as work:
            self.assertEqual(work.group_status('ab').status, 'published')
            reread = work.publish_group('ab')
            self.assertEqual(reread.report_ids, ('G-2:ab:A', 'G-2:ab:B'))
            class_a = work.read(reread.report_ids[0])
            self.assertEqual(class_a.record.draft.p_value, Fraction(1, 128))
            self.assertEqual(class_a.parent.revision, 1)
            self.assert_audit(work, 300, 0, 200)
            with self.assertRaisesRegex(ValueError, 'conflicting members'):
                work.request_group('ab', [['A', 'seven', 2], ['B', 'five', 1]])
            scenario('g4', {'lost_phase': 'after_commit', 'correction': 'seven -> 2'},
                     {'resumed': 'published', 'A_revision': 1, 'A_p': [1, 128]},
                     {'resumed': reread.status, 'A_revision': class_a.parent.revision,
                      'A_p': [class_a.record.draft.p_value.numerator,
                              class_a.record.draft.p_value.denominator]},
                     {'published_bps': 300},
                     {'published_bps': work.audit('coat').published_bps},
                     ['desk/publication.py', 'analysis/groups.py', 'archive/readback.py'],
                     'A group result saved after commit replays its original reports.')

    def test_group_rejects_mixed_family(self):
        with self.open() as work:
            self.prepare_groups(work)
            work.register('other', 500, 'X', Fraction(1, 2), 100)
            with self.assertRaisesRegex(ValueError, 'one test family'):
                work.request_group('mix', [['A', 'seven', 1], ['X', 'five', 1]])
            self.assert_audit(work, 0, 0, 500)
