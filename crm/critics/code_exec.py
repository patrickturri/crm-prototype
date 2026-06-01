"""Sandboxed Python execution critic (§6.1) — implemented in Phase 2.

Validity = reference impl passes its own tests AND >=1 adversarial test,
executed in a sandbox (§6.2): subprocess, wall-clock timeout, no network,
ephemeral temp dir, restricted builtins, memory cap.
"""

from __future__ import annotations

from crm.critics.base import Critic, CritResult
from crm.types import Conjecture


class CodeExecCritic(Critic):
    name = "code_exec"

    def __init__(self, timeout_s: float = 5.0) -> None:
        self.timeout_s = timeout_s

    def check(self, conjecture: Conjecture) -> CritResult:
        raise NotImplementedError("CodeExecCritic is implemented in Phase 2.")
