"""TOOL-MISUSE — PRISMS-class tool-use failures (arXiv 2608.00218).

Public case: Agentic LLMs exhibit three consequential tool-use failures:

1. **validity** — invalid / incomplete arguments
2. **over-calling** — unnecessary tool calls when none are needed
3. **missing** — omitted calls when tools are required

PRISMS detects these with sparse probes; this module is the **runtime gate**
twin: refuse execution plans that exhibit the three classes before side effects.

Non-Ornament:
  Call ``gate_tool_misuse`` before executing a tool plan. Pair with
  ``gate_destructive`` for DROP/rm inventory and ``gate_receipts`` after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Mapping, Sequence

from groundcrew.closed_loop import ClosedLoopError, GateOutcome

MisuseClass = Literal["validity", "over_calling", "missing", "ok"]


@dataclass(frozen=True)
class ToolSchema:
    """Required argument contract for a named tool."""

    name: str
    required_args: tuple[str, ...] = ()
    # Optional: arg name → allowed type names ("str","int","float","bool","any")
    arg_types: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required_args": list(self.required_args),
            "arg_types": dict(self.arg_types),
        }


@dataclass(frozen=True)
class PlannedToolCall:
    """One proposed tool invocation (pre-execution)."""

    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "arguments": dict(self.arguments),
        }


@dataclass(frozen=True)
class ToolMisuseReport:
    """Classified misuse findings for a plan."""

    validity_ids: tuple[str, ...]
    over_call_ids: tuple[str, ...]
    missing_tools: tuple[str, ...]
    call_count: int
    classes: tuple[MisuseClass, ...]

    @property
    def has_misuse(self) -> bool:
        return bool(self.validity_ids or self.over_call_ids or self.missing_tools)

    def to_dict(self) -> dict[str, Any]:
        return {
            "validity_ids": list(self.validity_ids),
            "over_call_ids": list(self.over_call_ids),
            "missing_tools": list(self.missing_tools),
            "call_count": self.call_count,
            "classes": list(self.classes),
            "has_misuse": self.has_misuse,
        }


def _as_schema(item: ToolSchema | dict[str, Any]) -> ToolSchema:
    if isinstance(item, ToolSchema):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"schema must be ToolSchema or dict, got {type(item)!r}")
    name = str(item.get("name") or item.get("tool") or "").strip()
    if not name:
        raise ValueError("tool schema missing name")
    req = item.get("required_args") or item.get("required") or ()
    if isinstance(req, str):
        req_t: tuple[str, ...] = (req,)
    else:
        req_t = tuple(str(x) for x in req)
    types = item.get("arg_types") or item.get("types") or {}
    if not isinstance(types, Mapping):
        types = {}
    return ToolSchema(name=name, required_args=req_t, arg_types=dict(types))


def _as_call(item: PlannedToolCall | dict[str, Any], index: int = 0) -> PlannedToolCall:
    if isinstance(item, PlannedToolCall):
        return item
    if not isinstance(item, dict):
        raise TypeError(f"call must be PlannedToolCall or dict, got {type(item)!r}")
    cid = str(item.get("call_id") or item.get("id") or f"call_{index+1}").strip()
    name = str(item.get("name") or item.get("tool") or "").strip()
    if not name:
        raise ValueError(f"tool call {cid!r} missing name")
    args = item.get("arguments") or item.get("args") or item.get("params") or {}
    if not isinstance(args, dict):
        args = {"_raw": args}
    return PlannedToolCall(call_id=cid, name=name, arguments=dict(args))


def _type_ok(value: Any, expected: str) -> bool:
    exp = (expected or "any").strip().lower()
    if exp in {"", "any", "object"}:
        return True
    if exp in {"str", "string"}:
        return isinstance(value, str)
    if exp in {"int", "integer"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if exp in {"float", "number"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if exp in {"bool", "boolean"}:
        return isinstance(value, bool)
    if exp in {"list", "array"}:
        return isinstance(value, (list, tuple))
    if exp == "dict":
        return isinstance(value, dict)
    return True


def call_is_valid(call: PlannedToolCall, schema: ToolSchema | None) -> bool:
    """True when required args present and types match schema (if provided)."""
    if schema is None:
        # no schema — only reject completely empty name
        return bool(call.name)
    args = call.arguments or {}
    for key in schema.required_args:
        if key not in args or args[key] is None or args[key] == "":
            return False
        expected = schema.arg_types.get(key)
        if expected and not _type_ok(args[key], expected):
            return False
    for key, expected in schema.arg_types.items():
        if key in args and args[key] is not None and args[key] != "":
            if not _type_ok(args[key], expected):
                return False
    return True


def analyze_tool_misuse(
    calls: Sequence[PlannedToolCall | dict[str, Any]] | None,
    *,
    schemas: Sequence[ToolSchema | dict[str, Any]] | Mapping[str, ToolSchema | dict[str, Any]] | None = None,
    tools_required: bool = False,
    required_tools: Iterable[str] | None = None,
    tools_forbidden: bool = False,
    max_calls: int | None = None,
) -> ToolMisuseReport:
    """Classify validity / over-calling / missing failures on a tool plan.

    Args:
        calls: Planned tool calls (may be empty).
        schemas: Per-tool required-arg contracts (list or name→schema map).
        tools_required: If True and calls empty → missing class.
        required_tools: Tool names that must appear at least once.
        tools_forbidden: If True, any call is over-calling (answer-only turn).
        max_calls: Soft cap; excess calls tagged over-calling.
    """
    planned: list[PlannedToolCall] = []
    if calls:
        for i, c in enumerate(calls):
            planned.append(_as_call(c, i))

    schema_map: dict[str, ToolSchema] = {}
    if schemas is not None:
        if isinstance(schemas, Mapping):
            for k, v in schemas.items():
                if isinstance(v, ToolSchema):
                    s = v
                elif isinstance(v, dict):
                    d = dict(v)
                    if not d.get("name"):
                        d["name"] = str(k)
                    s = _as_schema(d)
                else:
                    s = ToolSchema(name=str(k))
                schema_map[s.name] = s
                schema_map[str(k)] = s
        else:
            for s in schemas:
                sc = _as_schema(s)
                schema_map[sc.name] = sc

    validity: list[str] = []
    for c in planned:
        sch = schema_map.get(c.name) or schema_map.get(c.name.lower())
        if not call_is_valid(c, sch):
            validity.append(c.call_id)

    over: list[str] = []
    if tools_forbidden and planned:
        over.extend(c.call_id for c in planned)
    if max_calls is not None and max_calls >= 0 and len(planned) > max_calls:
        over.extend(c.call_id for c in planned[max_calls:])

    missing: list[str] = []
    if tools_required and not planned:
        missing.append("*")
    if required_tools:
        present = {c.name for c in planned}
        for t in required_tools:
            name = str(t).strip()
            if name and name not in present:
                missing.append(name)

    classes: list[MisuseClass] = []
    if validity:
        classes.append("validity")
    if over:
        classes.append("over_calling")
    if missing:
        classes.append("missing")
    if not classes:
        classes.append("ok")

    return ToolMisuseReport(
        validity_ids=tuple(dict.fromkeys(validity)),
        over_call_ids=tuple(dict.fromkeys(over)),
        missing_tools=tuple(dict.fromkeys(missing)),
        call_count=len(planned),
        classes=tuple(classes),
    )


def gate_tool_misuse(
    calls: Sequence[PlannedToolCall | dict[str, Any]] | None = None,
    *,
    schemas: Sequence[ToolSchema | dict[str, Any]] | Mapping[str, ToolSchema | dict[str, Any]] | None = None,
    tools_required: bool = False,
    required_tools: Iterable[str] | None = None,
    tools_forbidden: bool = False,
    max_calls: int | None = None,
    refuse_validity: bool = True,
    refuse_over_calling: bool = True,
    refuse_missing: bool = True,
) -> GateOutcome:
    """Refuse plans with PRISMS-class tool misuse (arXiv 2608.00218).

    Rules:

    * Invalid args (validity) → **FAIL**
    * Over-calling when tools forbidden / over max_calls → **FAIL**
    * Missing required tools / empty when tools_required → **FAIL_LOUD**
      (missing is pre-generation boundary class — empty inventory)
    * Clean plan → **PASS**
    """
    try:
        report = analyze_tool_misuse(
            calls,
            schemas=schemas,
            tools_required=tools_required,
            required_tools=required_tools,
            tools_forbidden=tools_forbidden,
            max_calls=max_calls,
        )
    except (TypeError, ValueError) as exc:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=f"TOOL-MISUSE: invalid plan payload: {exc}",
            exit_code=2,
            human_required=True,
        )

    if refuse_missing and report.missing_tools:
        return GateOutcome(
            ok=False,
            verdict="FAIL_LOUD",
            reason=(
                f"TOOL-MISUSE/missing: required tool call(s) omitted "
                f"missing={list(report.missing_tools)[:8]} call_count={report.call_count} "
                f"— refuse answer-only path when tools are needed "
                f"(arXiv 2608.00218 PRISMS missing class)"
            ),
            exit_code=2,
            human_required=True,
            receipt_count=report.call_count,
            action="missing",
            risk="high_risk",
        )

    if refuse_validity and report.validity_ids:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TOOL-MISUSE/validity: {len(report.validity_ids)} call(s) with "
                f"invalid/incomplete arguments ids={list(report.validity_ids)[:8]} "
                f"— refuse execution (PRISMS validity class)"
            ),
            exit_code=1,
            human_required=True,
            receipt_count=report.call_count,
            action="validity",
            risk="high_risk",
            empty_effect_ids=report.validity_ids[:20],
        )

    if refuse_over_calling and report.over_call_ids:
        return GateOutcome(
            ok=False,
            verdict="FAIL",
            reason=(
                f"TOOL-MISUSE/over_calling: {len(report.over_call_ids)} unnecessary "
                f"call(s) ids={list(report.over_call_ids)[:8]} "
                f"(tools_forbidden={tools_forbidden} max_calls={max_calls}) — "
                f"refuse surplus tool use (PRISMS over-calling class)"
            ),
            exit_code=1,
            human_required=False,
            receipt_count=report.call_count,
            action="over_calling",
            risk="safe",
            empty_effect_ids=report.over_call_ids[:20],
        )

    return GateOutcome(
        ok=True,
        verdict="PASS",
        reason=(
            f"TOOL-MISUSE ok: calls={report.call_count} classes={list(report.classes)}"
        ),
        exit_code=0,
        human_required=False,
        receipt_count=report.call_count,
        action="ok",
        risk="safe",
    )


def assert_tool_misuse_ok(
    calls: Sequence[PlannedToolCall | dict[str, Any]] | None = None,
    **kwargs: Any,
) -> GateOutcome:
    """Raise :class:`ClosedLoopError` unless :func:`gate_tool_misuse` is ok."""
    outcome = gate_tool_misuse(calls, **kwargs)
    if not outcome.ok:
        raise ClosedLoopError(f"{outcome.verdict}: {outcome.reason}")
    return outcome
