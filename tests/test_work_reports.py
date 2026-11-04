"""A scope handoff must match the exact typed assignment, never a prose guess."""

import json

import pytest

from deermate.work_reports import scope_report, work_prompt


def test_exact_scope_report_and_ordinary_tasks():
    report = {
        "version": 1,
        "work_id": "work",
        "operation_id": "op",
        "scope": "out_of_scope",
        "reason": "Another project is needed",
    }
    prompt = work_prompt("work", "op", "demo", "bounded request")
    assert scope_report(prompt, json.dumps(report)) == report
    assert scope_report("ordinary task", json.dumps(report)) is None
    assert scope_report(prompt, "I think this is out of scope") is None


@pytest.mark.parametrize(
    "change",
    [
        {"operation_id": "other"},
        {"work_id": "foreign"},
        {"version": 2},
        {"scope": "publish"},
        {"reason": "x" * 1001},
        {"extra": "instruction"},
    ],
)
def test_invalid_or_foreign_report_is_not_a_handoff(change):
    report = {
        "version": 1,
        "work_id": "work",
        "operation_id": "op",
        "scope": "out_of_scope",
        "reason": "bounded",
        **change,
    }
    assert scope_report(work_prompt("work", "op", "demo", "request"), json.dumps(report)) is None
