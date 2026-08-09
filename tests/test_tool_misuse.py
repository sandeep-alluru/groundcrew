"""TOOL-MISUSE - PRISMS-class validity / over-calling / missing (arXiv 2608.00218)."""

from __future__ import annotations

import pytest

from groundcrew.closed_loop import ClosedLoopError
from groundcrew.tool_misuse import (
    PlannedToolCall,
    ToolSchema,
    analyze_tool_misuse,
    assert_tool_misuse_ok,
    call_is_valid,
    gate_tool_misuse,
)


def test_validity_missing_required_arg() -> None:
    schemas = [ToolSchema("search", required_args=("q",))]
    calls = [PlannedToolCall("c1", "search", arguments={})]
    out = gate_tool_misuse(calls, schemas=schemas)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "validity" in out.reason.lower()
    assert "c1" in out.empty_effect_ids


def test_validity_type_mismatch() -> None:
    schemas = {
        "run": ToolSchema("run", required_args=("n",), arg_types={"n": "int"}),
    }
    calls = [{"call_id": "c1", "name": "run", "args": {"n": "not-int"}}]
    out = gate_tool_misuse(calls, schemas=schemas)
    assert out.ok is False
    assert out.verdict == "FAIL"


def test_valid_call_passes() -> None:
    schemas = [ToolSchema("search", required_args=("q",), arg_types={"q": "str"})]
    calls = [PlannedToolCall("c1", "search", {"q": "agent tools"})]
    out = gate_tool_misuse(calls, schemas=schemas)
    assert out.ok is True
    assert out.verdict == "PASS"


def test_missing_when_tools_required() -> None:
    out = gate_tool_misuse([], tools_required=True)
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert "missing" in out.reason.lower()


def test_missing_required_tool_name() -> None:
    calls = [PlannedToolCall("c1", "search", {"q": "x"})]
    out = gate_tool_misuse(
        calls,
        required_tools=["db_query"],
        schemas=[ToolSchema("search", ("q",))],
    )
    assert out.ok is False
    assert out.verdict == "FAIL_LOUD"
    assert "db_query" in out.reason


def test_over_calling_when_forbidden() -> None:
    calls = [PlannedToolCall("c1", "search", {"q": "x"})]
    out = gate_tool_misuse(calls, tools_forbidden=True)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "over" in out.reason.lower()


def test_over_calling_max_calls() -> None:
    calls = [
        PlannedToolCall("a", "t", {}),
        PlannedToolCall("b", "t", {}),
        PlannedToolCall("c", "t", {}),
    ]
    out = gate_tool_misuse(calls, max_calls=1)
    assert out.ok is False
    assert out.verdict == "FAIL"
    assert "b" in out.empty_effect_ids or "c" in out.empty_effect_ids


def test_analyze_report() -> None:
    r = analyze_tool_misuse(
        [],
        tools_required=True,
        tools_forbidden=False,
    )
    assert r.has_misuse is True
    assert "missing" in r.classes
    assert r.to_dict()["call_count"] == 0


def test_call_is_valid_no_schema() -> None:
    assert call_is_valid(PlannedToolCall("1", "x", {}), None) is True


def test_assert_raises() -> None:
    with pytest.raises(ClosedLoopError):
        assert_tool_misuse_ok([], tools_required=True)


def test_arxiv_prisms_fixture() -> None:
    """End-to-end three-class fixture from arXiv 2608.00218."""
    schemas = {
        "code_exec": {
            "name": "code_exec",
            "required_args": ["code"],
            "arg_types": {"code": "str"},
        },
        "search": {"name": "search", "required": ["q"]},
    }

    # validity: empty code
    bad = gate_tool_misuse(
        [{"id": "v1", "tool": "code_exec", "arguments": {"code": ""}}],
        schemas=schemas,
    )
    assert bad.ok is False
    assert bad.verdict == "FAIL"

    # over-calling: tools forbidden (pure reasoning turn)
    over = gate_tool_misuse(
        [{"call_id": "o1", "name": "search", "args": {"q": "x"}}],
        schemas=schemas,
        tools_forbidden=True,
    )
    assert over.ok is False
    assert "over" in over.reason.lower()

    # missing: need search but none planned
    miss = gate_tool_misuse(
        [],
        required_tools=["search"],
        schemas=schemas,
    )
    assert miss.ok is False
    assert miss.verdict == "FAIL_LOUD"

    # clean
    ok = gate_tool_misuse(
        [
            {"call_id": "1", "name": "search", "arguments": {"q": "prisms"}},
            {"call_id": "2", "name": "code_exec", "arguments": {"code": "print(1)"}},
        ],
        schemas=schemas,
        required_tools=["search"],
        max_calls=5,
    )
    assert ok.ok is True
    assert ok.verdict == "PASS"
