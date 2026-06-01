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
