# Workflow

Use the task thread as the shared record. The coordinator moves work between roles and keeps each handoff clear; no separate run files or checker are required by this workflow.

## Roles

- **Coordinator:** owns the task, decides whether separate roles are useful, accepts the plan, and keeps work within project policy. Route approval and policy decisions to the designated human.
- **Planner:** investigates without editing. Proposes a bounded plan with scope, assumptions, risks, acceptance criteria, and validation guidance.
- **Executor:** implements only the accepted scope. Reports what changed, what was validated, and any deviations or blockers.
- **Reviewer:** independently inspects the changes and evidence without editing. Reports concrete findings and recommends acceptance, changes, or escalation.

## Handoffs

1. **Plan:** The coordinator gives the planner the task and relevant project instructions. The planner returns a concise plan. The coordinator accepts it or resolves open questions before implementation.
2. **Execute:** The coordinator gives the executor the accepted plan and task context. The executor follows project security and dependency rules, performs the required validation, and reports evidence in the task thread.
3. **Review:** The reviewer checks the changed work against the accepted plan and project policies. A review should point to specific changes or missing evidence.
4. **Fix or stop:** If the reviewer requests changes, allow one executor fix-and-review pass. If the reviewer still cannot accept the result, or the task needs a policy or risk decision, stop and ask the project owner.
5. **Integrate:** The project’s designated owner handles commits, merges, pushes, deployment, or any other integration step under that project’s policy.

## Working rules

- A planner does not approve its own plan, and an executor does not review its own changes.
- Keep scope changes visible in the task thread and get coordinator acceptance before expanding the work.
- Do not claim validation that was not run. Report skipped checks and why they were skipped.
- This workflow is guidance, not an enforcement mechanism. Follow the target project’s instructions when they are stricter or more specific.
