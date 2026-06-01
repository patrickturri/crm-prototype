"""Lean 4 / mathlib critic (§6.3) — headline; implemented in Phase 4.

Compiles `import Mathlib; theorem crm_candidate : <stmt> := <proof>` via
`lake env lean`, mapping failures to reason classes. Uses prebuilt mathlib
oleans (`lake exe cache get`) — never compiles mathlib from source.
"""

from __future__ import annotations

from crm.critics.base import Critic, CritResult
from crm.types import Conjecture


class LeanCritic(Critic):
    name = "lean"

    def __init__(self, project_dir: str | None = None, timeout_s: float = 60.0) -> None:
        self.project_dir = project_dir
        self.timeout_s = timeout_s

    def check(self, conjecture: Conjecture) -> CritResult:
        raise NotImplementedError("LeanCritic is implemented in Phase 4.")
