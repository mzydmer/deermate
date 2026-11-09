## Outcome

Describe the concrete problem and resulting behavior. Mark any design-only or simulated behavior explicitly.

## Validation

Include relevant evidence, upstream versions, and material limits. For docs-only changes, check links and rendering.

## Boundaries

Describe any changes to credentials, host access, task recovery, or publishing rights. Never include secrets or private data.

## Spec and project tracking

Reference affected FR/NFR or feature-spec criteria. For meaningful behavior changes, update SPEC, STATUS, EVOLUTION, roadmap, and ADRs where applicable. Distinguish implementation, verification, merge, and release state. Small documentation corrections need only the relevant edits and link checks.

## Product documentation impact (required)

- [ ] Reviewed [documentation policy](../docs/DOCUMENTATION_POLICY.md) against this change.
- [ ] Updated affected customer guides / technical articles and pending changelog, or linked a reasoned `docs/change-notes/` record for internal-only changes.
- [ ] Regenerated the documentation catalog and passed `python scripts/product_docs.py --base <task-base>`.

Affected articles or no-update record:

## Design contract

- [ ] For UI changes, read design.md and reuse app/marketing recipes within their scope.
- [ ] Run python scripts/design_gate.py; include affected pages, themes and responsive checks.
- [ ] Update design.md for intended token changes, regenerate assets, and explain the reason.
- [ ] Report visual/keyboard limitations separately; passing the static gate is not browser acceptance.
