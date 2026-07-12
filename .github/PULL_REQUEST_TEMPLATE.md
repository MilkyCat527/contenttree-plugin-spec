# Summary

<!-- What does this PR change and why? -->

## Checklist

### G1 — domain neutrality

- [ ] Every new/changed schema property is meaningful for **any**
      deferred-capable plugin, not just a specific vendor/use case.
- [ ] If this PR adds a schema/OpenAPI field, the PR description (or linked
      issue) states the G1 rationale explicitly.
- [ ] No domain-specific/vendor-specific field was added to a shared
      whitelist (e.g. the 11-property completion-event / operation-status
      event shape) without independent justification.

### G3 — no SDK / no reference implementation

- [ ] This PR does not add or depend on a reference SDK or product
      implementation code.
- [ ] Any test-local "guard" logic (e.g. state-machine transition tables)
      is clearly documented as test data, not a reusable implementation.
- [ ] No implementation-repository code was consulted, copied, or
      referenced while authoring this change.

### Conformance

- [ ] `pip install -r requirements.txt && python -m pytest tests/` passes
      locally with no network access required.
- [ ] New/changed fixtures have a corresponding `fixtures/index.json` entry
      with target schema + expected valid/invalid outcome kept **outside**
      the fixture instance (never an in-band `__schema__`-style marker).
- [ ] `CHANGELOG.md` updated under `[Unreleased]` (no release claimed
      unless this PR is itself the release PR).

## Test results

<!-- Paste exact `pytest -q` output / counts here. -->
