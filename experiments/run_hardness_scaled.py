"""Scaled hardness-separation experiment (settles review finding #4/#6).

The first-pass hardness experiment (`run_hardness_distribution.py`) had only TWO
trivial candidates, so "does the rich operator separate contentful from trivial"
could not be answered. This scaled version:

  1. Uses a LARGER, VARIED trivial pool (~11 vacuous/over-permissive claims) plus
     the contentful entries of the offline pool, so contentful-vs-trivial is a
     real two-sample comparison with a Mann-Whitney U p-value.
  2. Adds a THIRD hardness variant `rich_false` that counts a perturbed neighbour
     as "broken" ONLY when the critic refutes it with reason_class == "FALSE"
     (a genuine counterexample), EXCLUDING ILLFORMED/TIMEOUT. The default hardness
     conflates syntactic breakage (a mutation that won't parse) with semantic
     breakage; `rich_false` isolates the mathematical signal.

Everything is real sandbox execution, fully deterministic (no API, no MiniLM —
hardness does not use the embedder). Outputs:
  results/findings/hardness_scaled.json
  docs/findings/hardness_scaled.md
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from crm.critics.code_exec import CodeExecCritic
from crm.proposers_code import _POOL
from crm.types import Conjecture

try:
    from scipy.stats import mannwhitneyu
    _HAVE_SCIPY = True
except Exception:  # pragma: no cover
    _HAVE_SCIPY = False

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "results" / "findings"
DOCS_DIR = REPO / "docs" / "findings"

PERTURBATIONS = 32
SEED = 42

# Contentful entries of the offline pool (genuine identities). Indices 6 (FALSE
# digit-reverse) and 7 (constant-zero trivial) are excluded from "contentful".
_CONTENTFUL_POOL_IDX = [0, 1, 2, 3, 4, 5, 8, 9]

# Augmented trivial pool: a VARIED mix of vacuous / over-permissive claims. Two
# failure families on purpose:
#   (A) over-permissive property — satisfied by (almost) any f  -> SHOULD be
#       low-hardness (mutations don't break it).
#   (B) degenerate-but-pinned — a constant/identity impl whose property pins that
#       exact constant -> hardness is HIGH (mutating the constant breaks it), so
#       hardness does NOT flag these; the automation probe is what catches them.
# Keeping both families makes the honest point: hardness only separates family A.
# NOTE: every entry carries `tests` consistent with its impl. The CodeExecCritic
# returns ILLFORMED for any candidate (or perturbed neighbour) with NO own tests,
# so omitting tests would make every perturbation ILLFORMED and confound the
# FALSE-only signal. Fair own-tests let perturbations be genuinely evaluated.
_TRIVIAL_POOL: list[dict[str, str]] = [
    {"id": "triv_always_true", "family": "A",
     "reference_impl": "def f(n):\n    return n * n",
     "tests": "assert f(2) == 4\nassert f(3) == 9",
     "property": "lambda n: True", "domain": "[0, 100]",
     "nl_gloss": "property always True (vacuous)"},
    {"id": "triv_tautology", "family": "A",
     "reference_impl": "def f(n):\n    return n * n + 1",
     "tests": "assert f(2) == 5\nassert f(3) == 10",
     "property": "lambda n: f(n) == f(n)", "domain": "[0, 100]",
     "nl_gloss": "property is a tautology f(n)==f(n)"},
    {"id": "triv_nonneg", "family": "A",
     "reference_impl": "def f(n):\n    return n * n",
     "tests": "assert f(2) == 4\nassert f(3) == 9",
     "property": "lambda n: f(n) >= 0", "domain": "[0, 100]",
     "nl_gloss": "over-permissive: f(n)>=0 for a nonneg function"},
    {"id": "triv_typeonly", "family": "A",
     "reference_impl": "def f(n):\n    return 2 * n",
     "tests": "assert f(2) == 4\nassert f(3) == 6",
     "property": "lambda n: isinstance(f(n), int)", "domain": "[0, 100]",
     "nl_gloss": "type-only property isinstance(f(n), int)"},
    {"id": "triv_plus0", "family": "A",
     "reference_impl": "def f(n):\n    return 3 * n",
     "tests": "assert f(2) == 6\nassert f(3) == 9",
     "property": "lambda n: f(n) == f(n) + 0", "domain": "[0, 100]",
     "nl_gloss": "property f(n)==f(n)+0 (vacuous)"},
    {"id": "triv_ge_self_minus1", "family": "A",
     "reference_impl": "def f(n):\n    return n * n",
     "tests": "assert f(2) == 4\nassert f(3) == 9",
     "property": "lambda n: f(n) >= f(n) - 1", "domain": "[0, 100]",
     "nl_gloss": "always-true inequality f(n) >= f(n)-1"},
    {"id": "triv_const0", "family": "B",
     "reference_impl": "def f(n):\n    return 0",
     "tests": "assert f(3) == 0\nassert f(9) == 0",
     "property": "lambda n: f(n) == 0", "domain": "[0, 100]",
     "nl_gloss": "constant-zero impl pinned by property f(n)==0"},
    {"id": "triv_const1", "family": "B",
     "reference_impl": "def f(n):\n    return 1",
     "tests": "assert f(3) == 1\nassert f(9) == 1",
     "property": "lambda n: f(n) == 1", "domain": "[0, 100]",
     "nl_gloss": "constant-one impl pinned by property f(n)==1"},
    {"id": "triv_const7", "family": "B",
     "reference_impl": "def f(n):\n    return 7",
     "tests": "assert f(3) == 7\nassert f(9) == 7",
     "property": "lambda n: f(n) == 7", "domain": "[0, 100]",
     "nl_gloss": "constant-7 impl pinned by property"},
    {"id": "triv_identity", "family": "B",
     "reference_impl": "def f(n):\n    return n",
     "tests": "assert f(3) == 3\nassert f(9) == 9",
     "property": "lambda n: f(n) == n", "domain": "[0, 100]",
     "nl_gloss": "identity impl pinned by property f(n)==n"},
    {"id": "triv_double", "family": "B",
     "reference_impl": "def f(n):\n    return 2 * n",
     "tests": "assert f(3) == 6\nassert f(9) == 18",
     "property": "lambda n: f(n) == 2 * n", "domain": "[0, 100]",
     "nl_gloss": "f(n)=2n pinned by property f(n)==2n"},
]


def _conj(cid: str, entry: dict[str, str]) -> Conjecture:
    return Conjecture(
        id=cid,
        statement=entry.get("statement", entry.get("nl_gloss", cid)),
        extra={
            "reference_impl": entry["reference_impl"],
            "tests": entry.get("tests", ""),
            "property": entry.get("property", ""),
            "domain": entry.get("domain", "[1, 100]"),
        },
    )


def _candidates() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in _CONTENTFUL_POOL_IDX:
        e = _POOL[i]
        out.append({"id": f"pool_{i:02d}", "group": "contentful", "family": "-",
                    "label": e.get("nl_gloss", e["statement"][:55]),
                    "conjecture": _conj(f"pool_{i:02d}", e)})
    for e in _TRIVIAL_POOL:
        out.append({"id": e["id"], "group": "trivial", "family": e["family"],
                    "label": e["nl_gloss"], "conjecture": _conj(e["id"], e)})
    return out


def _hardness_variants(critic: CodeExecCritic, c: Conjecture) -> dict[str, float]:
    """Return {literal_any, rich_any, rich_false} for one conjecture.

    *_any  : neighbour 'broken' iff NOT cr.valid (FALSE or ILLFORMED or TIMEOUT).
    rich_false: neighbour 'broken' iff cr.reason_class == 'FALSE' only (genuine
                counterexample) — excludes syntactically-broken mutations.
    """
    out: dict[str, float] = {}
    for strategy in ("literal", "rich"):
        perts = critic.perturb(c, PERTURBATIONS, SEED, strategy=strategy)
        if not perts:
            out[f"{strategy}_any"] = 0.0
            if strategy == "rich":
                out["rich_false"] = 0.0
                out["rich_n"] = 0
                out["rich_n_false"] = 0
                out["rich_n_illformed"] = 0
            continue
        n = len(perts)
        n_invalid = 0
        n_false = 0
        n_illformed = 0
        for pc in perts:
            cr = critic.check(pc)
            if not cr.valid:
                n_invalid += 1
                if cr.reason_class == "FALSE":
                    n_false += 1
                else:
                    n_illformed += 1
        out[f"{strategy}_any"] = n_invalid / n
        if strategy == "rich":
            out["rich_false"] = n_false / n
            out["rich_n"] = n
            out["rich_n_false"] = n_false
            out["rich_n_illformed"] = n_illformed
    return out


def _stats(vals: list[float]) -> dict[str, Any]:
    if not vals:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
    return {"n": len(vals), "mean": round(statistics.mean(vals), 4),
            "std": round(statistics.pstdev(vals), 4),
            "min": round(min(vals), 4), "max": round(max(vals), 4)}


def _mwu(content: list[float], trivial: list[float]) -> dict[str, Any]:
    """Mann-Whitney U one-sided test: is contentful hardness > trivial?"""
    gap = (statistics.mean(content) if content else 0.0) - \
          (statistics.mean(trivial) if trivial else 0.0)
    res: dict[str, Any] = {"gap_content_minus_trivial": round(gap, 4)}
    if _HAVE_SCIPY and content and trivial and (len(set(content + trivial)) > 1):
        try:
            u, p = mannwhitneyu(content, trivial, alternative="greater")
            res["mwu_u"] = float(u)
            res["mwu_p_greater"] = round(float(p), 4)
        except Exception as e:  # pragma: no cover
            res["mwu_error"] = str(e)
    else:
        res["mwu_p_greater"] = None
    res["separates"] = bool(gap > 0.10 and (res.get("mwu_p_greater") is not None
                                            and res["mwu_p_greater"] < 0.05))
    return res


def main() -> None:
    critic = CodeExecCritic(seed=SEED)
    cands = _candidates()
    print(f"[hardness-scaled] {sum(1 for c in cands if c['group']=='contentful')} contentful, "
          f"{sum(1 for c in cands if c['group']=='trivial')} trivial; "
          f"P={PERTURBATIONS} per strategy")

    per: list[dict[str, Any]] = []
    for rec in cands:
        v = _hardness_variants(critic, rec["conjecture"])
        row = {"id": rec["id"], "group": rec["group"], "family": rec["family"],
               "label": rec["label"], **{k: round(val, 4) if isinstance(val, float) else val
                                          for k, val in v.items()}}
        per.append(row)
        print(f"  {rec['id']:20s} [{rec['group']:10s} {rec['family']}] "
              f"lit={row['literal_any']:.3f} rich_any={row['rich_any']:.3f} "
              f"rich_false={row['rich_false']:.3f} "
              f"(false={v.get('rich_n_false',0)}/illformed={v.get('rich_n_illformed',0)}/{v.get('rich_n',0)})")

    def vals(group: str, key: str, family: str | None = None) -> list[float]:
        return [r[key] for r in per if r["group"] == group
                and (family is None or r["family"] == family)
                and isinstance(r.get(key), (int, float))]

    variants = ["literal_any", "rich_any", "rich_false"]
    aggregate: dict[str, Any] = {}
    separation: dict[str, Any] = {}
    for key in variants:
        aggregate[key] = {
            "contentful": _stats(vals("contentful", key)),
            "trivial_all": _stats(vals("trivial", key)),
            "trivial_A_overpermissive": _stats(vals("trivial", key, "A")),
            "trivial_B_pinned": _stats(vals("trivial", key, "B")),
        }
        separation[key] = {
            "vs_all_trivial": _mwu(vals("contentful", key), vals("trivial", key)),
            "vs_family_A_only": _mwu(vals("contentful", key), vals("trivial", key, "A")),
        }

    output = {
        "meta": {"perturbations": PERTURBATIONS, "seed": SEED,
                 "n_contentful": sum(1 for c in cands if c["group"] == "contentful"),
                 "n_trivial": sum(1 for c in cands if c["group"] == "trivial"),
                 "n_trivial_A": sum(1 for c in cands if c["group"] == "trivial" and c["family"] == "A"),
                 "n_trivial_B": sum(1 for c in cands if c["group"] == "trivial" and c["family"] == "B"),
                 "scipy": _HAVE_SCIPY},
        "aggregate": aggregate,
        "separation": separation,
        "per_candidate": per,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "hardness_scaled.json").write_text(json.dumps(output, indent=2))
    _write_md(output, DOCS_DIR / "hardness_scaled.md")

    print("\n=== SEPARATION (contentful hardness > trivial?) ===")
    for key in variants:
        s_all = separation[key]["vs_all_trivial"]
        s_a = separation[key]["vs_family_A_only"]
        print(f"  {key:12s}  vs ALL trivial: gap={s_all['gap_content_minus_trivial']:+.3f} "
              f"p={s_all.get('mwu_p_greater')}  separates={s_all['separates']}  ||  "
              f"vs family-A only: gap={s_a['gap_content_minus_trivial']:+.3f} "
              f"p={s_a.get('mwu_p_greater')} separates={s_a['separates']}")
    print(f"\n[hardness-scaled] wrote {OUT_DIR/'hardness_scaled.json'} and {DOCS_DIR/'hardness_scaled.md'}")


def _write_md(o: dict, path: Path) -> None:
    m, agg, sep = o["meta"], o["aggregate"], o["separation"]

    def row(s: dict) -> str:
        if not s or s["n"] == 0:
            return "n/a | n/a | n/a | n/a | 0"
        return f"{s['mean']:.3f} | {s['std']:.3f} | {s['min']:.3f} | {s['max']:.3f} | {s['n']}"

    L = [
        "# Scaled hardness separation: does a richer operator make hardness discriminate?",
        "",
        "Settles **review finding #4/#6**. The first pass had only 2 trivial candidates;",
        f"this uses **{m['n_contentful']} contentful** vs **{m['n_trivial']} trivial** "
        f"({m['n_trivial_A']} over-permissive *family A*, {m['n_trivial_B']} degenerate-but-pinned *family B*),",
        f"P={m['perturbations']} perturbations/strategy, seed={m['seed']}, real sandbox execution (no API).",
        "",
        "Three hardness variants: **literal_any** (old: integer +-1, broken = not valid),",
        "**rich_any** (new operators/boundaries, broken = not valid), and **rich_false**",
        "(rich, broken = reason_class FALSE only — excludes syntactically-broken/ILLFORMED mutations).",
        "",
        "## Mean hardness by group",
        "",
        "| Variant | Group | Mean | Std | Min | Max | N |",
        "|---|---|---|---|---|---|---|",
    ]
    for key in ("literal_any", "rich_any", "rich_false"):
        a = agg[key]
        L.append(f"| {key} | contentful | {row(a['contentful'])} |")
        L.append(f"| {key} | trivial (all) | {row(a['trivial_all'])} |")
        L.append(f"| {key} | trivial A (over-permissive) | {row(a['trivial_A_overpermissive'])} |")
        L.append(f"| {key} | trivial B (pinned) | {row(a['trivial_B_pinned'])} |")
    L += ["", "## Separation test (one-sided Mann-Whitney: contentful > trivial)", "",
          "| Variant | vs all trivial: gap | p | separates | vs family-A: gap | p | separates |",
          "|---|---|---|---|---|---|---|"]
    for key in ("literal_any", "rich_any", "rich_false"):
        sa = sep[key]["vs_all_trivial"]
        sf = sep[key]["vs_family_A_only"]
        L.append(f"| {key} | {sa['gap_content_minus_trivial']:+.3f} | {sa.get('mwu_p_greater')} | "
                 f"{sa['separates']} | {sf['gap_content_minus_trivial']:+.3f} | {sf.get('mwu_p_greater')} | "
                 f"{sf['separates']} |")
    L += [
        "",
        "## Per-candidate",
        "",
        "| id | group | family | literal_any | rich_any | rich_false |",
        "|---|---|---|---|---|---|",
    ]
    for r in o["per_candidate"]:
        L.append(f"| {r['id']} | {r['group']} | {r['family']} | "
                 f"{r['literal_any']:.3f} | {r['rich_any']:.3f} | {r['rich_false']:.3f} |")
    L += ["", "---", "*Produced by `experiments/run_hardness_scaled.py`. Real sandbox execution, no fabrication.*"]
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
