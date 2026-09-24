# Workflow and handoff contract

The coordinator decides whether a task needs a written plan under the target project’s criteria. The checker verifies the recorded decision and its consequences; it does not choose planning policy or judge whether a plan is good.

## Roles

- **Coordinator:** creates the run, sets policy, decides whether planning is required, accepts or escalates a plan, starts each phase, and routes integration to the project-defined owner.
- **Planner:** read-only investigator who creates plan.json with scope, assumptions, risks, steps, acceptance criteria, and validation guidance.
- **Executor:** implements only the accepted plan and task scope, recording a result for every plan step, validation evidence, and deviations.
- **Reviewer:** read-only and independent; records findings and chooses accepted, changes_requested, or escalate.

The planner never records acceptance. The coordinator or a human records it in plan-acceptance.json.

## Files in one run directory

| File | Purpose |
| --- | --- |
| run.json | Run ID, planning decision, approval mode, remediation limit, and integration policy reference. |
| plan.json | Proposed plan, including stable step IDs and whether human approval is required. |
| plan-acceptance.json | Accepted/rejected/escalated decision bound to the plan digest and approver role. |
| executor-packet.json | Executor instructions, remediation pass, and plan path plus digest, or a justified planning skip. |
| executor-result.json | Status, evidence, and deviations for every planned step plus validation evidence. |
| review-result.json | Reviewer outcome and findings, tied to the exact executor result and plan digest. |
| integration-handoff.json | Accepted review and validation evidence handed to the integration policy owner. |

All contracts use schema version 1.0. JSON Schemas are in contracts/v1/. Contract documents reject unknown fields. References in a run directory must resolve within that directory. SHA-256 digests cover the referenced file’s exact raw bytes, including whitespace and newline.

## Gate sequence

1. Populate run.json. Set planning to required or skipped; a skip needs a rationale. Set approval mode to coordinator or human for plan acceptance, and choose a finite non-negative remediation pass limit. The template defaults to one pass.
2. If planning is required, the planner proposes plan.json. The coordinator or human accepts it in plan-acceptance.json; acceptance must match its plan ID and SHA-256 digest. Human approval is mandatory if the run policy selects human or the plan marks itself as requiring human approval.
3. Create executor-packet.json with the same run ID and a plan reference and digest. Run check_handoff.py RUN_DIRECTORY --phase executor. The checker rejects missing, malformed, unaccepted, mismatched, or out-of-directory plan references. If planning was skipped, the run and packet must both record the same non-empty rationale and must omit a plan reference.
4. The executor writes executor-result.json, mapping each plan step exactly once. The reviewer records review-result.json, which must reference the raw-byte digest of that executor result and the same plan digest. If review escalates or the remediation limit is exhausted, only a human can add a human_resolution with an accepted or blocked decision and a note.
5. Run the checker with phase review. An accepted review permits integration. changes_requested permits another executor pass only when remediation_pass is below the configured maximum. At the limit, or when the reviewer selects escalate, the checker exits with status 3 until a human records an accepted or blocked resolution. A human acceptance explicitly permits integration; a blocked resolution keeps the gate closed.
6. The designated integration owner records integration-handoff.json with accepted review, matching digests, a policy reference, and validation evidence. Phase integration is a readiness check only; it does not commit, merge, push, or deploy.

See [adapting-to-a-project.md](adapting-to-a-project.md) before copying the workflow into another repository.
