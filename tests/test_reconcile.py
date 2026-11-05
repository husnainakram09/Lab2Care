import json
import unittest
from pathlib import Path
from core.reconcile import reconcile_case, approval_is_current


DATA = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/demo_case.json').read_text())


class TestFictionalReconciliation(unittest.TestCase):
    def test_missing_third_report_is_not_closed(self):
        r = reconcile_case(DATA['patient_id'], DATA['orders'], DATA['reports'])
        self.assertEqual(r['missing_order_ids'], ['T-03'])
        self.assertFalse(r['ready_for_doctor_review'])

    def test_all_three_reports_can_be_checked(self):
        third = {'report_id': 'R-03', 'order_id': 'T-03', 'patient_id': 'PAT-001', 'test_code': 'LAB-C'}
        r = reconcile_case(DATA['patient_id'], DATA['orders'], DATA['reports'] + [third])
        self.assertEqual(r['missing_order_ids'], [])
        self.assertTrue(r['ready_for_doctor_review'])

    def test_wrong_patient_is_quarantined(self):
        third = {'report_id': 'R-03', 'order_id': 'T-03', 'patient_id': 'PAT-999', 'test_code': 'LAB-C'}
        r = reconcile_case(DATA['patient_id'], DATA['orders'], DATA['reports'] + [third])
        self.assertEqual(r['quarantined'][0]['reason'], 'patient_mismatch')
        self.assertIn('T-03', r['missing_order_ids'])

    def test_wrong_test_code_is_quarantined(self):
        third = {'report_id': 'R-03', 'order_id': 'T-03', 'patient_id': 'PAT-001', 'test_code': 'LAB-X'}
        r = reconcile_case(DATA['patient_id'], DATA['orders'], DATA['reports'] + [third])
        self.assertEqual(r['quarantined'][0]['reason'], 'test_code_mismatch')

    def test_duplicate_delivery_does_not_create_an_extra_accepted_report(self):
        r = reconcile_case(DATA['patient_id'], DATA['orders'], DATA['reports'] + [DATA['reports'][0]])
        self.assertEqual(r['duplicate_report_ids'], ['R-01'])
        self.assertEqual(len(r['accepted_report_ids']), 2)

    def test_unrecognized_order_is_quarantined(self):
        alien = {'report_id': 'R-X', 'order_id': 'T-99', 'patient_id': 'PAT-001', 'test_code': 'LAB-X'}
        r = reconcile_case(DATA['patient_id'], DATA['orders'], DATA['reports'] + [alien])
        self.assertEqual(r['quarantined'][0]['reason'], 'unknown_order')

    def test_stale_doctor_approval_is_invalid(self):
        self.assertFalse(approval_is_current(3, 4))
        self.assertTrue(approval_is_current(4, 4))


if __name__ == '__main__':
    unittest.main()
