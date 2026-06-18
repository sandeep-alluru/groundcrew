"""Semantic action codec: content-addressed action specs and verifiable receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from groundcrew.snapshot import SnapshotDiff


@dataclass
class ActionSpec:
    """A semantic description of an action: a verb applied to a target with params."""

    verb: str
    target: str
    params: dict
    id: str = field(init=False)

    def __post_init__(self):
        payload = f"{self.verb}|{self.target}|{json.dumps(self.params, sort_keys=True)}"
        self.id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "verb": self.verb,
            "target": self.target,
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, d) -> ActionSpec:
        return cls(verb=d["verb"], target=d["target"], params=d["params"])


@dataclass
class ActionReceipt:
    """A verifiable record pairing an action spec with the state change it produced."""

    spec: ActionSpec
    before_id: str
    after_id: str
    diff: SnapshotDiff
    success: bool
    timestamp: float
    id: str = field(init=False)

    def __post_init__(self):
        payload = json.dumps(
            {
                "spec_id": self.spec.id,
                "before_id": self.before_id,
                "after_id": self.after_id,
                "success": self.success,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
        )
        self.id = hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "spec": self.spec.to_dict(),
            "before_id": self.before_id,
            "after_id": self.after_id,
            "diff": self.diff.to_dict(),
            "success": self.success,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d) -> ActionReceipt:
        spec = ActionSpec.from_dict(d["spec"])
        diff = SnapshotDiff.from_dict(d["diff"])
        return cls(
            spec=spec,
            before_id=d["before_id"],
            after_id=d["after_id"],
            diff=diff,
            success=d["success"],
            timestamp=d["timestamp"],
        )
