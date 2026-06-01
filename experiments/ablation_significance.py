"""Significance ablation (§9.2) — tests the reward-hack guard. Phase 3.

Critic on (trivial survivors -> score 0, excluded) vs off (any valid counts).
Metric: fraction of survivors that are trivial/vacuous. Expected: sharply lower
with the critic on.
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError("Significance ablation is implemented in Phase 3.")


if __name__ == "__main__":
    raise SystemExit(main())
