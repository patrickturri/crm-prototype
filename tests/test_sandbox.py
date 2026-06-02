"""Sandbox security + CodeExecCritic tests (§6.1, §6.2).

NON-NEGOTIABLE (§3.6, §6.2, §15): arbitrary generated code must NOT be able to
reach the network or touch the host filesystem outside its ephemeral sandbox.
These tests PROVE both, by actually running adversarial programs in the sandbox
and asserting they are blocked — not by mocking.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from crm.critics.code_exec import CodeExecCritic
from crm.proposers_code import OfflineCodeProposer
from crm.sandbox import run_in_sandbox
from crm.types import Conjecture


# ---------------------------------------------------------------------------
# 1. The sandbox blocks an OUTBOUND NETWORK connection.
# ---------------------------------------------------------------------------

def test_sandbox_blocks_outbound_network_socket():
    """Opening a raw socket / connecting out must be blocked."""
    code = (
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.connect(('8.8.8.8', 53))\n"
        "print('CONNECTED')\n"
    )
    res = run_in_sandbox(code, timeout_s=5.0)
    # Must NOT have connected. Either explicitly blocked, or an error — never ok.
    assert res.status != "ok"
    assert "CONNECTED" not in res.stdout_tail
    assert res.status == "blocked" or "network" in res.detail.lower() or \
        "socket" in res.detail.lower()


def test_sandbox_blocks_urllib_network():
    """Higher-level HTTP libs must also be blocked from phoning home."""
    code = (
        "import urllib.request\n"
        "urllib.request.urlopen('http://example.com', timeout=3)\n"
        "print('FETCHED')\n"
    )
    res = run_in_sandbox(code, timeout_s=8.0)
    assert res.status != "ok"
    assert "FETCHED" not in res.stdout_tail


# ---------------------------------------------------------------------------
# 2. The sandbox blocks an OUT-OF-SANDBOX FILESYSTEM WRITE.
# ---------------------------------------------------------------------------

def test_sandbox_blocks_out_of_sandbox_filesystem_write():
    """Writing to an absolute path outside the sandbox root must be blocked,
    and the file must NOT appear on the host afterwards."""
    target = Path(tempfile.gettempdir()) / "crm_escape_proof.txt"
    if target.exists():
        target.unlink()
    code = (
        f"open({str(target)!r}, 'w').write('escaped')\n"
        "print('WROTE')\n"
    )
    res = run_in_sandbox(code, timeout_s=5.0)
    try:
        assert res.status != "ok"
        assert "WROTE" not in res.stdout_tail
        assert res.status == "blocked" or "filesystem" in res.detail.lower()
        # The decisive proof: the host file was NOT created.
        assert not target.exists(), "candidate escaped the sandbox FS guard!"
    finally:
        if target.exists():
            target.unlink()


def test_sandbox_blocks_write_to_home_dir():
    """A write to the user's home dir (a classic escape) must be blocked."""
    target = Path(os.path.expanduser("~")) / ".crm_escape_proof.txt"
    if target.exists():
        target.unlink()
    code = f"open({str(target)!r}, 'w').write('x')\nprint('WROTE')\n"
    res = run_in_sandbox(code, timeout_s=5.0)
    try:
        assert res.status != "ok"
        assert not target.exists()
    finally:
        if target.exists():
            target.unlink()


# ---------------------------------------------------------------------------
# 3. The sandbox enforces a hard wall-clock TIMEOUT.
# ---------------------------------------------------------------------------

def test_sandbox_enforces_wallclock_timeout():
    code = "while True:\n    pass\n"
    res = run_in_sandbox(code, timeout_s=1.5)
    assert res.status == "timeout"
    assert res.elapsed_s < 6.0  # killed promptly, not hung


# ---------------------------------------------------------------------------
# 4. Legitimate pure-compute code still RUNS and PASSES inside the sandbox.
# ---------------------------------------------------------------------------

def test_sandbox_allows_legit_computation():
    code = (
        "def f(n):\n"
        "    return sum(range(n + 1))\n"
        "assert f(5) == 15\n"
        "assert f(0) == 0\n"
    )
    res = run_in_sandbox(code, timeout_s=5.0)
    assert res.status == "ok", res.detail


def test_sandbox_allows_writing_inside_sandbox_root():
    """Writing a RELATIVE file (lands in the ephemeral sandbox cwd) is fine."""
    code = (
        "open('scratch.txt', 'w').write('hello')\n"
        "assert open('scratch.txt').read() == 'hello'\n"
    )
    res = run_in_sandbox(code, timeout_s=5.0)
    assert res.status == "ok", res.detail


# ---------------------------------------------------------------------------
# 5. CodeExecCritic end-to-end: real survive/die on real execution.
# ---------------------------------------------------------------------------

def test_codeexec_critic_validates_correct_task():
    """A correct task with an independent property survives (PROVED)."""
    critic = CodeExecCritic(timeout_s=5.0, n_adversarial=10)
    c = Conjecture(
        id="c0",
        statement="f(n) = sum of first n odd numbers; equals n*n",
        extra={
            "reference_impl": "def f(n):\n    return sum(2*i+1 for i in range(n))",
            "tests": "assert f(1) == 1\nassert f(4) == 16",
            "property": "lambda n: f(n) == n*n",
            "domain": "[0, 100]",
        },
    )
    cr = critic.check(c)
    assert cr.valid is True
    assert cr.reason_class == "PROVED"
    assert cr.proof_method == "tests_passed"


def test_codeexec_critic_catches_false_task_via_adversarial():
    """A WRONG impl that passes the proposer's own tests is caught by the
    independently-generated adversarial tests (NOT LLM judgement)."""
    critic = CodeExecCritic(timeout_s=5.0, n_adversarial=20)
    c = Conjecture(
        id="c1",
        statement="double digit-reverse returns n",
        extra={
            # FALSE in general: fails on multiples of 10 (120 -> 21 -> 12).
            "reference_impl": "def f(n):\n    return int(str(int(str(n)[::-1]))[::-1])",
            "tests": "assert f(123) == 123",          # passes its OWN test
            "property": "lambda n: f(n) == n",        # independent claim
            "domain": "[1, 300]",
        },
    )
    cr = critic.check(c)
    assert cr.valid is False
    assert cr.reason_class == "FALSE"


def test_codeexec_critic_ill_formed_task():
    critic = CodeExecCritic(timeout_s=5.0)
    c = Conjecture(id="c2", statement="broken", extra={
        "reference_impl": "def f(n)\n    return n",  # syntax error
        "tests": "assert f(1) == 1",
        "property": "lambda n: True",
        "domain": "[1, 10]",
    })
    cr = critic.check(c)
    assert cr.valid is False
    assert cr.reason_class == "ILLFORMED"


def test_offline_proposer_produces_runnable_tasks():
    """The offline fallback emits tasks the critic can really run (>=1 survives)."""
    prop = OfflineCodeProposer()
    critic = CodeExecCritic(timeout_s=5.0, n_adversarial=8)
    batch = prop.propose("ctx", k=8, seed=0)
    results = [critic.check(c) for c in batch]
    assert any(r.valid for r in results), "no offline task survived the critic"


# ---------------------------------------------------------------------------
# 6. perturb() mutation strategies (review finding #6 — A/B-able hardness).
# ---------------------------------------------------------------------------

def _sum_first_n_odds_conjecture() -> Conjecture:
    return Conjecture(
        id="pc0",
        statement="f(n) = sum of first n odd numbers; equals n*n",
        extra={
            "reference_impl": "def f(n):\n    return sum(2*i+1 for i in range(n))",
            "tests": "assert f(1) == 1\nassert f(4) == 16",
            "property": "lambda n: f(n) == n*n",
            "domain": "[0, 100]",
        },
    )


def _neighbour_keys(neighbours) -> set[tuple[str, str]]:
    return {
        (n.extra.get("reference_impl", ""), n.extra.get("property", ""))
        for n in neighbours
    }


def test_perturb_literal_is_byte_identical_to_default():
    """strategy='literal' MUST reproduce the original (default) behaviour
    byte-for-byte so the two strategies can be A/B'd against the same survivors.
    """
    critic = CodeExecCritic(timeout_s=5.0)
    c = _sum_first_n_odds_conjecture()
    # default arg == explicit "literal"
    default = critic.perturb(c, p=999, seed=0)
    literal = critic.perturb(c, p=999, seed=0, strategy="literal")
    assert _neighbour_keys(default) == _neighbour_keys(literal)
    # every literal neighbour differs from the base only in an integer literal
    base_impl = c.extra["reference_impl"]
    base_prop = c.extra["property"]
    for n in literal:
        ni = n.extra.get("reference_impl", "")
        np = n.extra.get("property", "")
        # exactly one of the two fields changed; the other is byte-identical
        assert (ni == base_impl) != (np == base_prop)


def test_perturb_semantic_adds_non_numeric_neighbours():
    """strategy='semantic' yields >0 neighbours that the literal strategy never
    produces (operator/boundary rewrites, not integer +-1)."""
    critic = CodeExecCritic(timeout_s=5.0)
    c = _sum_first_n_odds_conjecture()
    literal = _neighbour_keys(critic.perturb(c, p=999, seed=0, strategy="literal"))
    semantic = _neighbour_keys(critic.perturb(c, p=999, seed=0, strategy="semantic"))
    extra = semantic - literal
    assert len(extra) > 0, "semantic produced no neighbours beyond literal"
    # the semantic set must contain at least one operator-swap rewrite
    swapped = [
        impl for (impl, _prop) in semantic
        if "range(n)" not in impl or "//" in impl or "-" in impl
    ]
    assert swapped


def test_perturb_rich_is_superset_of_literal_and_semantic():
    """strategy='rich' = literal ∪ semantic."""
    critic = CodeExecCritic(timeout_s=5.0)
    c = _sum_first_n_odds_conjecture()
    literal = _neighbour_keys(critic.perturb(c, p=999, seed=0, strategy="literal"))
    semantic = _neighbour_keys(critic.perturb(c, p=999, seed=0, strategy="semantic"))
    rich = _neighbour_keys(critic.perturb(c, p=999, seed=0, strategy="rich"))
    assert literal <= rich
    assert semantic <= rich
    assert rich == (literal | semantic)


def test_perturb_semantic_neighbours_are_runnable_and_break_contentful():
    """Every semantic neighbour is a real, sandbox-runnable candidate; for a
    CONTENTFUL claim the operator/boundary edits actually break it (real
    execution, not a heuristic) — i.e. hardness is non-degenerate."""
    critic = CodeExecCritic(timeout_s=5.0, n_adversarial=10)
    c = _sum_first_n_odds_conjecture()
    neighbours = critic.perturb(c, p=20, seed=0, strategy="semantic")
    assert neighbours, "expected semantic neighbours"
    broke = 0
    for n in neighbours:
        cr = critic.check(n)
        if not cr.valid:
            broke += 1
    # a genuinely contentful identity is broken by most operand/operator edits
    assert broke > 0, "no semantic neighbour broke a contentful claim"
