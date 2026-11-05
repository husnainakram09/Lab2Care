"""Deterministic report/order reconciliation for fictional hackathon data only.

No clinical interpretation. This module is independent of any framework, VM,
model provider, or repository structure and can be adapted after team approval.
"""
from __future__ import annotations


def reconcile_case(patient_id: str, orders: list[dict], reports: list[dict]) -> dict:
    """Link reports to an order only when the fictional identity and test code match.

    Returns a typed-by-convention dict for an initial workflow contract.
    A report with an unknown order, wrong patient, or wrong test code is quarantined.
    """
    order_map = {o['order_id']: o for o in orders}
    if len(order_map) != len(orders):
        raise ValueError('Duplicate order_id in case')
    seen_report_ids: set[str] = set()
    accepted: dict[str, dict] = {}
    quarantined: list[dict] = []
    duplicate_report_ids: list[str] = []

    for report in reports:
        report_id = report['report_id']
        if report_id in seen_report_ids:
            duplicate_report_ids.append(report_id)
            continue
        seen_report_ids.add(report_id)
        order = order_map.get(report['order_id'])
        reason = None
        if order is None:
            reason = 'unknown_order'
        elif order['patient_id'] != patient_id or report['patient_id'] != patient_id:
            reason = 'patient_mismatch'
        elif report['test_code'] != order['test_code']:
            reason = 'test_code_mismatch'
        elif report['order_id'] in accepted:
            reason = 'multiple_reports_needs_review'
        if reason:
            quarantined.append({'report_id': report_id, 'reason': reason})
        else:
            accepted[report['order_id']] = report

    missing = [o['order_id'] for o in orders if o['order_id'] not in accepted]
    return {
        'accepted_report_ids': [r['report_id'] for r in accepted.values()],
        'missing_order_ids': missing,
        'quarantined': quarantined,
        'duplicate_report_ids': duplicate_report_ids,
        'ready_for_doctor_review': not missing and not quarantined,
    }


def approval_is_current(approved_case_version: int, current_case_version: int) -> bool:
    """An approval cannot authorize actions after source case state changed."""
    return approved_case_version == current_case_version
