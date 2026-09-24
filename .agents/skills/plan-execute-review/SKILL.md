---
name: plan-execute-review
description: Coordinate substantial project tasks through a versioned planning, execution, review, and integration handoff. Use when separate roles and explicit handoff evidence improve control.
---

# Plan, execute, review

Coordinate one bounded task through planning, execution, independent review, any configured remediation, and an integration handoff.

Before using this workflow in a repository, read [adapting the workflow](references/adapting-to-a-project.md) and inspect the target project’s instructions and policies. Apply its security, approval, validation, and Git boundaries. This kit does not grant permission to modify, commit, merge, or publish project changes.

The coordinator owns the run artifacts and phase transitions. The planner proposes a plan; it does not approve its own plan. The executor works only from an accepted packet. The reviewer independently assesses the execution result. Integration remains with the owner designated by the project adapter.

Use the [workflow reference](references/workflow.md) for artifact fields, checker phases, and remediation. Start from the [minimal run templates](../../../templates/minimal-run/). Before handing work to an executor, run the checker with phase executor; validate each subsequent handoff with phase review and integration.

If required planning is skipped, record the reason in the run policy and executor packet. If approval or review escalates, stop the gated transition and route the decision to the project’s designated human or coordinator. Do not turn a failed check into approval by editing evidence or weakening the contract.
