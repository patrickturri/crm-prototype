"""Lean 4 / mathlib critic (§6.3) — the HEADLINE real critic.

Reality-grounding (§3, §15): validity is decided by the Lean **kernel**, never by
a language model. For each conjecture we write a `Mathlib`-importing file::

    import Mathlib
    set_option maxHeartbeats 400000 in
    theorem crm_candidate : <statement> := <proof_attempt>

and compile it with ``lake env lean <file>`` (so the prebuilt mathlib oleans on
``LEAN_PATH`` are visible) under a per-candidate wall-clock timeout. Then::

    valid = (exit code 0) AND (no error diagnostics) AND (no `sorry`)

Failure mapping (§6.3):
  * type / parse / elaboration error                 -> ILLFORMED
  * unsolved goals / proof incomplete within budget  -> UNPROVEN_BUDGET
  * refuted (e.g. `decide`/`omega` reports false)     -> FALSE
  * compile exceeded the per-candidate timeout       -> TIMEOUT
  * uses `sorry` / `admit` / `sorryAx`                -> UNPROVEN_BUDGET

If the **supplied** proof fails, we optionally retry ONCE with a battery of
automation tactics (`by decide`, `by omega`, `by simp`, `by aesop`) and, on
success, record ``proof_method`` accordingly. This distinguishes a hand proof
("supplied") from an automation-closed one ("omega"/"decide"/...), which feeds
``is_trivial`` in the significance critic (§5.2): a statement closed by
automation alone is trivial.

NON-FATAL toolchain policy (§6.3, §15): if the Lean toolchain / mathlib is not
available in this environment, the critic does NOT crash the build. Construct it
with ``require_available=False`` (the default used by the loop) and every
``check`` returns a clearly-labelled ``ILLFORMED`` result with
``detail="lean toolchain unavailable: <reason>"`` so the run completes and the
code-critic floor still stands. ``LeanCritic.available()`` reports the real
toolchain status, and ``scripts/setup_lean.sh`` is what makes it available.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from crm.critics.base import CritResult
from crm.types import Conjecture

# Default project dir created by scripts/setup_lean.sh (overridable via config /
# the CRM_LEAN_PROJECT env var).
DEFAULT_PROJECT_DIR = os.environ.get(
    "CRM_LEAN_PROJECT",
    str(Path(__file__).resolve().parents[2] / ".lean" / "crm_lean"),
)

# Automation tactics tried (in order) on a one-shot retry when the supplied
# proof fails. Order matters: cheap/decisive first. The tactic name is recorded
# as proof_method so the significance critic can detect automation-closure.
AUTOMATION_TACTICS: list[tuple[str, str]] = [
    ("decide", "by decide"),
    ("omega", "by omega"),
    ("simp", "by simp"),
    ("norm_num", "by norm_num"),
    ("aesop", "by aesop"),
]

_SORRY_RE = re.compile(r"\b(sorry|admit|sorryAx)\b")
# Lean diagnostics are emitted as `file:line:col: error: ...` / `warning: ...`.
_ERROR_RE = re.compile(r"\berror:", re.IGNORECASE)
_UNSOLVED_RE = re.compile(r"unsolved goals|declaration uses 'sorry'|linarith failed", re.IGNORECASE)
_REFUTED_RE = re.compile(
    r"failed to (?:reduce to|prove)|tactic 'decide' (?:proved|failed)|"
    r"reduced to 'False'|of type 'False'|expected .* but is false",
    re.IGNORECASE,
)


def _theorem_file(statement: str, proof_attempt: str) -> str:
    """Assemble the `import Mathlib` candidate file (§6.3)."""
    proof = (proof_attempt or "").strip()
    if not proof:
        proof = "by sorry"
    return (
        "import Mathlib\n"
        "set_option maxHeartbeats 400000 in\n"
        f"theorem crm_candidate : {statement} := {proof}\n"
    )


class LeanCritic:
    """Reality-grounded Lean 4 / mathlib critic (§6.3).

    Parameters
    ----------
    project_dir:
        The Lake project (with prebuilt mathlib oleans) created by
        ``scripts/setup_lean.sh``. Defaults to ``<repo>/.lean/crm_lean``.
    timeout_s:
        Per-candidate wall-clock timeout for ``lake env lean`` (§6.3).
    automation_retry:
        If True (default), a failed supplied proof triggers ONE retry across the
        automation battery; the closing tactic (if any) is recorded as
        ``proof_method``.
    require_available:
        If True, ``__init__`` raises when the toolchain is missing (used by an
        explicit Lean-only run). The loop uses the default (False): an absent
        toolchain yields labelled ILLFORMED results instead of crashing (§6.3
        non-fatal policy).
    """

    name = "lean"

    def __init__(
        self,
        project_dir: str | None = None,
        timeout_s: float = 60.0,
        automation_retry: bool = True,
        require_available: bool = False,
        tactics: list[str] | None = None,
    ) -> None:
        self.project_dir = str(project_dir or DEFAULT_PROJECT_DIR)
        self.timeout_s = float(timeout_s)
        self.automation_retry = automation_retry
        # Automation battery (one-shot retry + is_trivial probe). Configurable so
        # the demo can trade breadth-of-tactics against per-candidate cost (each
        # `lake env lean` reloads `import Mathlib`, ~4s). Default = full battery.
        if tactics is None:
            self._tactics = list(AUTOMATION_TACTICS)
        else:
            tset = set(tactics)
            self._tactics = [(m, t) for (m, t) in AUTOMATION_TACTICS if m in tset]
        self._unavailable_reason: str | None = None
        self._cache: dict[str, CritResult] = {}

        ok, reason = self._probe()
        if not ok:
            self._unavailable_reason = reason
            if require_available:
                raise RuntimeError(f"Lean toolchain unavailable: {reason}")

    # ---- toolchain probing ---------------------------------------------
    def _probe(self) -> tuple[bool, str]:
        """Return (available, reason). Real check, no fabrication."""
        lake = shutil.which("lake")
        if lake is None:
            # elan may have installed lake under ~/.elan/bin without it being on
            # PATH in this shell; check there too.
            cand = Path.home() / ".elan" / "bin" / "lake"
            if cand.exists():
                lake = str(cand)
            else:
                return False, "`lake` not found on PATH (run scripts/setup_lean.sh)"
        self._lake = lake
        proj = Path(self.project_dir)
        if not proj.exists():
            return False, f"Lake project not found at {self.project_dir}"
        # Confirm the prebuilt mathlib oleans are present (cache get succeeded).
        lakefile = proj / "lakefile.lean"
        lakefile_toml = proj / "lakefile.toml"
        if not lakefile.exists() and not lakefile_toml.exists():
            return False, f"no lakefile in {self.project_dir}"
        return True, "ok"

    def available(self) -> bool:
        return self._unavailable_reason is None

    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    # ---- the survive/die decision --------------------------------------
    def check(self, conjecture: Conjecture) -> CritResult:
        t0 = time.perf_counter()
        stmt = (conjecture.statement or "").strip()
        proof = (conjecture.proof_attempt or "").strip()

        if self._unavailable_reason is not None:
            # Non-fatal: labelled, never a fabricated pass (§3, §6.3).
            return CritResult(
                False, "ILLFORMED",
                f"lean toolchain unavailable: {self._unavailable_reason}",
                None, time.perf_counter() - t0,
            )

        if not stmt:
            return CritResult(False, "ILLFORMED", "empty statement", None,
                              time.perf_counter() - t0)
        if _SORRY_RE.search(stmt) or _SORRY_RE.search(proof):
            return CritResult(False, "UNPROVEN_BUDGET", "contains `sorry`/`admit`",
                              None, time.perf_counter() - t0)

        # Cache by (statement, proof, budget) so identical candidates across
        # seeds/rounds aren't recompiled (§11).
        ckey = self._cache_key(stmt, proof)
        if ckey in self._cache:
            cached = self._cache[ckey]
            return CritResult(cached.valid, cached.reason_class, cached.detail,
                              cached.proof_method, 0.0)

        # First attempt: the supplied proof.
        cr = self._compile(stmt, proof, proof_method="supplied")
        if cr.valid:
            self._cache[ckey] = cr
            return CritResult(cr.valid, cr.reason_class, cr.detail,
                              cr.proof_method, time.perf_counter() - t0)

        # One-shot automation retry (§6.3): try to CLOSE it with a tactic.
        if self.automation_retry and cr.reason_class in (
            "UNPROVEN_BUDGET", "ILLFORMED", "FALSE",
        ):
            for method, tactic in self._tactics:
                cr2 = self._compile(stmt, tactic, proof_method=method)
                if cr2.valid:
                    self._cache[ckey] = cr2
                    return CritResult(cr2.valid, cr2.reason_class, cr2.detail,
                                      cr2.proof_method, time.perf_counter() - t0)
                # A `decide`/`omega` that reduces the goal to False is a genuine
                # refutation -> the statement is FALSE (§6.3).
                if cr2.reason_class == "FALSE":
                    cr = cr2

        self._cache[ckey] = cr
        return CritResult(cr.valid, cr.reason_class, cr.detail, cr.proof_method,
                          time.perf_counter() - t0)

    def _cache_key(self, stmt: str, proof: str) -> str:
        h = hashlib.sha256(
            f"{stmt}\x00{proof}\x00{self.timeout_s}\x00lean".encode("utf-8")
        ).hexdigest()
        return h

    # ---- the actual compile -------------------------------------------
    def _compile(self, statement: str, proof: str, proof_method: str) -> CritResult:
        """Compile one candidate via ``lake env lean`` and classify the result."""
        src = _theorem_file(statement, proof)
        proj = Path(self.project_dir)
        # Ephemeral temp file INSIDE the project so relative imports resolve, but
        # cleaned up after.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".lean", dir=str(proj), delete=False, encoding="utf-8"
        ) as fh:
            fh.write(src)
            fpath = fh.name
        try:
            try:
                proc = subprocess.run(
                    [self._lake, "env", "lean", fpath],
                    cwd=str(proj),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )
            except subprocess.TimeoutExpired:
                return CritResult(False, "TIMEOUT",
                                  f"lake env lean exceeded {self.timeout_s}s",
                                  None, 0.0)
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            return self._classify(proc.returncode, out, proof_method)
        finally:
            try:
                os.unlink(fpath)
            except OSError:
                pass

    def _classify(self, returncode: int, output: str, proof_method: str) -> CritResult:
        """Map (exit code, diagnostics) -> CritResult (§6.3)."""
        # `sorry` slipping through the elaborator => not proved.
        if _SORRY_RE.search(output):
            return CritResult(False, "UNPROVEN_BUDGET",
                              "proof uses sorry/admit", None, 0.0)

        if returncode == 0 and not _ERROR_RE.search(output):
            # Clean compile, no errors, no sorry => the kernel accepted it.
            detail = (
                f"compiled (proof_method={proof_method})"
                if proof_method == "supplied"
                else f"closed by `{proof_method}`"
            )
            return CritResult(True, "PROVED", detail, proof_method, 0.0)

        # Non-zero / errors present: classify the failure honestly.
        snippet = _first_error(output)
        if _REFUTED_RE.search(output):
            return CritResult(False, "FALSE", f"refuted: {snippet}", None, 0.0)
        if _UNSOLVED_RE.search(output):
            return CritResult(False, "UNPROVEN_BUDGET",
                              f"unsolved goals: {snippet}", None, 0.0)
        # Otherwise a type/parse/elaboration error => ill-formed.
        return CritResult(False, "ILLFORMED", f"elaboration error: {snippet}",
                          None, 0.0)

    # ---- significance hooks -------------------------------------------
    def automation_closeable(self, statement: str) -> bool:
        """True iff `decide`/`omega`/`simp`/`norm_num` ALONE closes `statement`.

        This is the §5.2 ``is_trivial`` automation axis and the §5.3 "not cheaply
        derivable" clause, decided by REALLY running the tactics in Lean (not a
        heuristic). If the toolchain is unavailable, we cannot decide and
        conservatively return False (so nothing is falsely flagged trivial).
        """
        if self._unavailable_reason is not None:
            return False
        if not statement or _SORRY_RE.search(statement):
            return False
        for _method, tactic in self._tactics:
            cr = self._compile(statement, tactic, proof_method=_method)
            if cr.valid:
                return True
        return False

    def perturb(self, conjecture: Conjecture, p: int, seed: int) -> list[Conjecture]:
        """Generate up to `p` statement perturbations for the hardness signal.

        Delegates to the shared string/AST perturbation operators (§5.2) on the
        Lean statement; each neighbour is recompiled by ``check`` (automation
        allowed, same budget). A contentful theorem is surrounded by false
        neighbours (high hardness); a trivial truth by true ones.
        """
        from crm.perturb import generate_perturbations

        perts = generate_perturbations(conjecture.statement, p, seed=seed)
        out: list[Conjecture] = []
        for i, pt in enumerate(perts):
            out.append(
                Conjecture(
                    id=f"{conjecture.id}_pert{i}",
                    statement=pt.text,
                    proof_attempt="",  # automation retry decides each neighbour
                    nl_gloss=getattr(pt, "note", "") or "perturbation",
                    round=conjecture.round,
                )
            )
        return out


# Lean prefixes diagnostics with `<abs path>.lean:line:col:`. Strip the local
# file path so it never leaks into the ledger / genealogy / SURVIVORS.md.
_DIAG_PREFIX_RE = re.compile(r"^\S*?\.lean:(\d+:\d+:)\s*")


def _strip_path(line: str) -> str:
    return _DIAG_PREFIX_RE.sub(r"\1 ", line).strip()


def _first_error(output: str) -> str:
    """Return a short, single-line, path-free snippet of the first error."""
    for line in output.splitlines():
        if _ERROR_RE.search(line):
            return _strip_path(line.strip())[:200]
    # Fall back to the first non-empty line.
    for line in output.splitlines():
        s = line.strip()
        if s:
            return _strip_path(s)[:200]
    return "(no diagnostics)"
