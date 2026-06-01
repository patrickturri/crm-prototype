"""Genealogy ablation (§9.1) — tests H2. Implemented in Phase 3.

Treatment mode="genealogy" vs control mode="control", everything else identical
(same proposer/model/topic/k/rounds/critic/budgets), >=3 seeds, mean +/- std.
Primary metric: cumulative certified-novel survivors vs round.
"""

from __future__ import annotations


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError("Genealogy ablation is implemented in Phase 3.")


if __name__ == "__main__":
    raise SystemExit(main())
