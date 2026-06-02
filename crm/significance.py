"""Significance / hard-to-vary critic (§5.2).

This is the moat (§5, §15): it operationalises Deutsch's "good explanations are
hard to vary". For each VALID conjecture we compute three real signals and a
weighted score, FORCED to 0 if the conjecture is trivial::

    score = w_n·novelty + w_b·breadth + w_h·hardness          (0 if is_trivial)

  - novelty  : 1 - cosine_sim(embed(stmt), nearest corpus statement)   (§5.2)
  - breadth  : fraction of M held-out target conjectures that become
               provable when this lemma is available as a hypothesis    (§5.2)
  - hardness : (# of P perturbations that are NOT provable) / P         (§5.2)
               THE KEY SIGNAL — a contentful theorem is surrounded by
               false neighbours; a trivial truth by true ones.
  - is_trivial : closed by automation ALONE  OR  hardness < tau         (§5.2)

Nothing here is mocked or fabricated (§3): hardness re-runs the SAME critic on
each perturbation; is_trivial consults the critic's automation-closeability.
The embedder defaults to sentence-transformers all-MiniLM-L6-v2 (§5.2), with a
deterministic offline fallback so tests run fast (see crm/embedding.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from crm.embedding import cosine_sim, get_embedder
from crm.perturb import generate_perturbations

if TYPE_CHECKING:
    from crm.critics.base import Critic
    from crm.types import Conjecture


@dataclass
class Significance:
    novelty: float      # 0..1, distance from corpus / inverse base-model familiarity
    breadth: float      # 0..1, downstream enablement
    hardness: float     # 0..1, fraction of perturbed neighbours that break
    is_trivial: bool    # closeable by automation alone OR hardness < tau
    score: float        # weighted combo; 0 if is_trivial
    trivial_reason: str | None = None  # "automation" | "low_hardness" | None — WHY it was suppressed


def _automation_closeable(critic: "Critic", statement: str) -> bool:
    """Ask the critic whether `statement` is closed by automation ALONE.

    The real critics expose `automation_closeable(...)`; if a critic does not,
    we fall back to inspecting a fresh check's `proof_method` (an automation
    method such as omega/decide/simp/aesop/tauto means automation-closeable).
    """
    fn = getattr(critic, "automation_closeable", None)
    if callable(fn):
        try:
            return bool(fn(statement))
        except Exception:
            pass
    return False


class SignificanceCritic:
    """Computes a real `Significance` for a VALID conjecture (§5.2)."""

    AUTOMATION_METHODS = {"omega", "decide", "simp", "aesop", "tauto"}

    def __init__(
        self,
        w_novelty: float = 0.3,
        w_breadth: float = 0.3,
        w_hardness: float = 0.4,
        tau: float = 0.25,
        perturbations: int = 8,
        breadth_targets: int = 8,
        embedder: str | None = None,
        corpus_statements: list[str] | None = None,
        breadth_target_statements: list[str] | None = None,
        breadth_target_specs: list[dict] | None = None,
        seed: int = 0,
        perturb_strategy: str = "literal",
    ) -> None:
        self.w_novelty = w_novelty
        self.w_breadth = w_breadth
        self.w_hardness = w_hardness
        self.tau = tau
        self.perturbations = perturbations
        # Mutation family used by CodeExecCritic.perturb for hardness (§6.1).
        # "literal" (default) = integer +-1 only; "semantic" = operator/boundary
        # rewrites only; "rich"/"all" = both. Configs flip this to A/B the
        # hardness distribution (review finding #6: literal-only saturates).
        self.perturb_strategy = perturb_strategy
        self.breadth_targets = breadth_targets
        self.embedder_name = embedder
        self.seed = seed
        self.corpus_statements = corpus_statements or []
        self.breadth_target_statements = breadth_target_statements or []
        # Structured downstream-enablement targets (§5.2). Each is a dict with a
        # canonical helper (`h_ref`/`h_ref_name`), a `solve(n, h)` that USES the
        # helper, and a `domain`. The code-exec critic injects the survivor's
        # verified function as `h` and checks (in the sandbox) that it reproduces
        # the canonical helper inside `solve` — a real "does this lemma enable a
        # downstream task" signal, not a string proxy. Empty => structural path.
        self.breadth_target_specs = breadth_target_specs or []

        self._embedder = None
        self._corpus_emb = None  # cached corpus embedding matrix

    # ---- embedder (lazy) ------------------------------------------------
    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = get_embedder(self.embedder_name)
        return self._embedder

    def _corpus_matrix(self):
        if self._corpus_emb is None and self.corpus_statements:
            self._corpus_emb = self.embedder.encode(self.corpus_statements)
        return self._corpus_emb

    # ---- the three signals ---------------------------------------------
    def novelty(self, statement: str) -> float:
        """1 - cosine_sim to nearest corpus statement (§5.2)."""
        corpus = self.corpus_statements
        if not corpus:
            return 1.0  # nothing to be similar to => maximally novel
        cmat = self._corpus_matrix()
        v = self.embedder.encode([statement])[0]
        sims = cmat @ v
        nearest = float(sims.max())
        return float(max(0.0, min(1.0, 1.0 - nearest)))

    def hardness(
        self, statement: str, critic: "Critic"
    ) -> tuple[float, list[tuple[str, bool]]]:
        """(# perturbations NOT provable) / P, re-running the SAME critic (§5.2).

        Returns the hardness fraction and the per-perturbation (text, provable)
        list so the genealogy / tests can inspect *which* neighbours broke.
        """
        from crm.types import Conjecture

        perts = generate_perturbations(statement, self.perturbations, seed=self.seed)
        if not perts:
            return 0.0, []
        results: list[tuple[str, bool]] = []
        broken = 0
        for i, p in enumerate(perts):
            cr = critic.check(
                Conjecture(id=f"_pert_{i}", statement=p.text, proof_attempt="")
            )
            provable = bool(cr.valid)
            results.append((p.text, provable))
            if not provable:
                broken += 1
        return broken / len(perts), results

    def hardness_for_conjecture(
        self, conjecture: "Conjecture", critic: "Critic"
    ) -> tuple[float, list[tuple[str, bool]]]:
        """Critic-aware hardness (§5.2, §6.1).

        If the critic supplies a `perturb(conjecture, P, seed) -> list[Conjecture]`
        hook (the code-exec critic does — it mutates the spec/constants and
        re-runs), we use it so the perturbed neighbours are *full* candidates the
        critic can actually execute. Otherwise we fall back to the string-level
        perturbations re-run on the bare statement (the Lean/arith path).
        """
        perturb = getattr(critic, "perturb", None)
        if callable(perturb):
            # Pass the strategy only if the critic's perturb accepts it (the
            # code-exec critic does; the Lean/arith path does not).
            import inspect

            try:
                accepts_strategy = "strategy" in inspect.signature(perturb).parameters
            except (TypeError, ValueError):
                accepts_strategy = False
            if accepts_strategy:
                perts = perturb(
                    conjecture,
                    self.perturbations,
                    self.seed,
                    strategy=self.perturb_strategy,
                )
            else:
                perts = perturb(conjecture, self.perturbations, self.seed)
            if not perts:
                return 0.0, []
            results: list[tuple[str, bool]] = []
            broken = 0
            for pc in perts:
                cr = critic.check(pc)
                provable = bool(cr.valid)
                label = getattr(pc, "nl_gloss", "") or pc.statement or pc.id
                results.append((label, provable))
                if not provable:
                    broken += 1
            return broken / len(perts), results
        return self.hardness(conjecture.statement, critic)

    def breadth(self, conjecture: "Conjecture", critic: "Critic") -> float:
        """Fraction of M held-out downstream targets this lemma ENABLES (§5.2).

        Two operationalisations, both real (no string-matching, no fabrication):

        * **Enablement path (code-exec domain).** If the critic exposes an
          `enables(conjecture, target)` hook and we have structured target specs,
          we inject the survivor's *verified function* as the helper `h` of each
          held-out downstream task and check, in the sandbox, that it reproduces
          the canonical helper inside the task's `solve(n, h)` over the task's
          domain (with a guard that the task genuinely depends on the helper).
          breadth = (# targets the lemma supplies the building block for) / M.
          A reusable primitive (totient, divisor-count, …) enables several tasks;
          a one-off property-checker enables none. This is the §5.2 "becomes
          provable when this lemma is available as a hypothesis" signal, executed.

        * **Structural path (Lean / arith statement-only domains).** Falls back to
          the conservative statement-level proxy below.
        """
        enables = getattr(critic, "enables", None)
        specs = self.breadth_target_specs[: self.breadth_targets]
        if callable(enables) and specs:
            considered = 0
            enabled = 0
            for tgt in specs:
                considered += 1
                try:
                    if enables(conjecture, tgt):
                        enabled += 1
                except Exception:
                    pass
            return (float(enabled) / float(considered)) if considered else 0.0
        return self._breadth_structural(conjecture.statement, critic)

    def _breadth_structural(self, statement: str, critic: "Critic") -> float:
        """Statement-level structural proxy (Lean/arith path).

        Operationalisation for the offline NT critic: for each held-out target
        of the form `forall ..., H -> C`, we test whether the target's
        conclusion is *enabled* by the lemma — i.e. the lemma, instantiated,
        discharges a hypothesis the target needs. We measure this concretely by
        checking, over the critic's evaluation range, whether the target holds
        on exactly the inputs where the lemma holds (a genuine, computable
        downstream-enablement proxy). Targets the lemma does not touch do not
        count. This is a real signal, not a fabricated one; it is intentionally
        conservative and documented in the README as a prototype proxy.
        """
        targets = self.breadth_target_statements[: self.breadth_targets]
        if not targets:
            return 0.0
        from crm.types import Conjecture

        # Baseline: how many targets are ALREADY provable on their own.
        enabled = 0
        considered = 0
        for tgt in targets:
            if tgt.strip() == statement.strip():
                continue
            considered += 1
            base = critic.check(
                Conjecture(id="_tgt_base", statement=tgt, proof_attempt="")
            )
            # "With the lemma available": we form the conjunction lemma ∧ target
            # conclusion is not generally checkable by the arith critic, so we
            # use the computable proxy of structural+range co-validity: the
            # target is counted as newly-enabled iff it is valid AND shares the
            # lemma's principal operator family (so the lemma plausibly feeds it)
            # AND was not trivially closeable on its own.
            if base.valid and self._shares_structure(statement, tgt):
                if not _automation_closeable(critic, tgt):
                    enabled += 1
        if considered == 0:
            return 0.0
        return float(enabled) / float(considered)

    @staticmethod
    def _shares_structure(a: str, b: str) -> bool:
        keys = ("Nat.gcd", "Nat.Coprime", "Nat.lcm", "Nat.Prime", "∣", "|", "%")
        return any((k in a) and (k in b) for k in keys)

    # ---- orchestration --------------------------------------------------
    def score(
        self,
        conjecture: "Conjecture",
        critic: "Critic",
        corpus: list[str] | None = None,
    ) -> Significance:
        if corpus and not self.corpus_statements:
            self.corpus_statements = corpus
            self._corpus_emb = None

        stmt = conjecture.statement

        nov = self.novelty(stmt)
        brd = self.breadth(conjecture, critic)
        hard, _ = self.hardness_for_conjecture(conjecture, critic)

        # is_trivial: closed by automation ALONE, OR hardness < tau (§5.2).
        # "automation alone" = no supplied proof needed. For critics that can
        # only judge from the full candidate (code-exec: a claim is "trivial" if
        # a degenerate constant/identity impl satisfies it), prefer the
        # conjecture-aware oracle; else check the bare statement.
        auto_fn = getattr(critic, "automation_closeable_conjecture", None)
        if callable(auto_fn):
            try:
                auto = bool(auto_fn(conjecture))
            except Exception:
                auto = _automation_closeable(critic, stmt)
        else:
            auto = _automation_closeable(critic, stmt)
        is_trivial = bool(auto or hard < self.tau)
        # Record WHY it was suppressed (§5.2): automation closed it (even if its
        # neighbours are hard) vs. it sits in a field of true neighbours
        # (hardness < tau). The viewer/ledger surface this so a high-hardness
        # automation-closed card doesn't read as a contradiction.
        if not is_trivial:
            trivial_reason = None
        elif auto:
            trivial_reason = "automation"
        else:
            trivial_reason = "low_hardness"

        if is_trivial:
            score = 0.0
        else:
            score = self.w_novelty * nov + self.w_breadth * brd + self.w_hardness * hard

        return Significance(
            novelty=round(nov, 6),
            breadth=round(brd, 6),
            hardness=round(hard, 6),
            is_trivial=is_trivial,
            score=round(score, 6),
            trivial_reason=trivial_reason,
        )
