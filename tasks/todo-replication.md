# Layer 1 — independent adversarial replication gate

Goal: after WRITING, an INDEPENDENT replicator agent re-derives the paper's headline
number from the data and stress-tests it across alternative specifications; the engine
assesses sign-stability deterministically and gates (force reframe if fragile). Catches
the failure the skeptic can't: specification-fragile / overstated headline findings.

## Build order
- [ ] ReplicationReport model + config (enable_replication_gate, replication_max_specs,
      replication_sign_stability_threshold). Off by default, on in default.yaml.
- [ ] _REPLICATOR_PROMPT (constants.py): adversarial — identify headline claim, RE-DERIVE
      it, stress-test under N specs, print structured RESULT tokens (recomputed, per-spec
      sign/value, n_specs, n_same_sign, headline_reproduced).
- [ ] ReplicationHandler (orchestrator/replication.py): build prompt from paper+data, run
      an independent-role agent, execute code in sandbox (reuse executor/workspace/data),
      parse tokens, compute verdict (reproduced / fragile / not_reproduced).
- [ ] Engine: run after reflection loop, before internal review; store state.replication_report.
- [ ] Review: editor prompt gains the report + a mandatory check — an unreframed headline
      the replication found fragile/unreproduced is BLOCKING.
- [ ] Tests: verdict assessment logic (deterministic), token parsing, config, prompt content,
      gate wiring. Full suite green.

## Design decisions (proceeding with recommended defaults)
- Fragile/unreproduced -> FORCE REFRAME (blocking review requirement), not hard-reject.
- Replicator uses a configurable "replicator" role so operators can point it at a different
  model for genuine independence; falls back to a capable default.
