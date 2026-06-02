"""Test H-novelty-is-score: is certify_novel driven by the novelty gate alone?

Deterministic post-hoc analysis over all committed ledgers. No API, no embedder.
For each scored conjecture we have significance.{novelty,breadth,hardness,is_trivial}
and the recorded certified_novel. We measure the discriminative power (Mann-Whitney
AUC) of each significance feature for certified-vs-noncertified among non-trivial
records, and check whether the novelty>=0.35 gate is necessary/predictive.

Writes results/findings/hyp_H-novelty-is-score.json.
"""

from __future__ import annotations

import glob
import json
import os
import statistics as st
import sys


def auc(pos: list[float], neg: list[float]) -> float:
    """Mann-Whitney AUC = P(score_pos > score_neg), ties counted as 0.5."""
    if not pos or not neg:
        return float("nan")
    wins = ties = 0
    for a in pos:
        for b in neg:
            if a > b:
                wins += 1
            elif a == b:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def load_records(pattern: str) -> list[dict]:
    recs: list[dict] = []
    for f in sorted(glob.glob(pattern, recursive=True)):
        with open(f) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return recs


def analyze(pattern: str = "results/**/ledger.jsonl") -> dict:
    e = load_records(pattern)
    v = [r for r in e if r.get("significance")]
    sig = lambda r: r["significance"]
    nontriv = [r for r in v if not sig(r)["is_trivial"]]
    cert = [r for r in nontriv if r["certified_novel"]]
    nc = [r for r in nontriv if not r["certified_novel"]]

    res: dict = {
        "n_ledger_files": len(sorted(glob.glob(pattern, recursive=True))),
        "n_records_total": len(e),
        "n_records_with_significance": len(v),
        "n_nontrivial": len(nontriv),
        "n_certified_nontrivial": len(cert),
        "n_noncertified_nontrivial": len(nc),
    }
    for feat in ("hardness", "breadth", "novelty"):
        cp = [sig(r)[feat] for r in cert]
        npv = [sig(r)[feat] for r in nc]
        res[f"{feat}_cert_mean"] = round(st.mean(cp), 4)
        res[f"{feat}_cert_std"] = round(st.pstdev(cp), 4)
        res[f"{feat}_noncert_mean"] = round(st.mean(npv), 4)
        res[f"{feat}_noncert_std"] = round(st.pstdev(npv), 4)
        res[f"{feat}_auc_cert_vs_noncert"] = round(auc(cp, npv), 4)

    res["novelty_gate_predicts_certify_frac_among_nontrivial"] = round(
        sum(1 for r in nontriv if (sig(r)["novelty"] >= 0.35) == r["certified_novel"])
        / len(nontriv),
        4,
    )
    gate = lambda r: sig(r)["novelty"] >= 0.35 and not sig(r)["is_trivial"]
    res["combined_gate_predicts_certify_frac_all_valid"] = round(
        sum(1 for r in v if gate(r) == r["certified_novel"]) / len(v), 4
    )
    res["certified_violating_gate"] = sum(
        1 for r in v if r["certified_novel"] and (sig(r)["novelty"] < 0.35 or sig(r)["is_trivial"])
    )
    res["gatepass_not_certified"] = sum(
        1 for r in v if gate(r) and not r["certified_novel"]
    )
    res["gatefail_certified"] = sum(
        1 for r in v if not gate(r) and r["certified_novel"]
    )
    gp = [r for r in v if gate(r)]
    res["gatepass_frac_breadth_zero"] = round(
        sum(1 for r in gp if sig(r)["breadth"] == 0) / len(gp), 4
    )
    res["gatepass_hardness_mean"] = round(st.mean([sig(r)["hardness"] for r in gp]), 4)
    res["gatepass_hardness_std"] = round(st.pstdev([sig(r)["hardness"] for r in gp]), 4)

    # Verdict logic: SUPPORTED iff hardness & breadth AUC ~ 0.5 (no power),
    # novelty separates, and the novelty gate is strictly necessary.
    hardness_no_power = abs(res["hardness_auc_cert_vs_noncert"] - 0.5) < 0.05
    breadth_no_power = abs(res["breadth_auc_cert_vs_noncert"] - 0.5) < 0.05
    novelty_separates = res["novelty_auc_cert_vs_noncert"] > 0.6
    gate_necessary = res["certified_violating_gate"] == 0 and res["gatefail_certified"] == 0
    res["verdict"] = (
        "SUPPORTED"
        if (hardness_no_power and breadth_no_power and novelty_separates and gate_necessary)
        else "REFUTED_OR_INCONCLUSIVE"
    )
    return res


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pattern = argv[0] if argv else "results/**/ledger.jsonl"
    res = analyze(pattern)
    os.makedirs("results/findings", exist_ok=True)
    out = "results/findings/hyp_H-novelty-is-score.json"
    with open(out, "w") as fh:
        json.dump(res, fh, indent=2)
    print(json.dumps(res, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
