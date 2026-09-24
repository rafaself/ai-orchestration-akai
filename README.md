# AI Orchestration Akai

A reusable, Codex-first workflow kit for coordinating a bounded Plan → Execute → Review cycle, then handing accepted work to the project’s integration owner.

This repository contains a repository skill, Codex role profiles, versioned JSON contracts and templates, and a read-only Python checker. The checker validates handoff readiness; it does not start agents, persist state, or perform Git operations.

## Adapt before using

The workflow is generic. **Adapt it to each project before enabling it.** Review that project’s AGENTS.md, security and data policies, approval boundaries, development tools, test strategy, and integration rules. In particular, each project must decide who can commit, merge, or push and what requires human approval. The included agent profiles are examples to copy and tailor, not universal permissions.

## Contents

- .agents/skills/plan-execute-review/ — coordinator skill and workflow references.
- .codex/agents/ — planner, executor, and reviewer profile examples.
- contracts/v1/ — machine-readable JSON Schemas for the v1 handoffs.
- templates/minimal-run/ — a complete passing run directory to copy and adapt.
- scripts/check_handoff.py — dependency-free phase and handoff validator.
- tests/ — standard-library tests for success, failure, approval, digest, and remediation behavior.

## Use in a project

1. Copy the skill folder into the project’s .agents/skills/ directory.
2. Review and adapt the three agent profiles before copying them into the project’s .codex/agents/ directory.
3. Copy templates/minimal-run/ to a run directory and fill in its task, planning decision, approval mode, and integration policy reference.
4. If a plan is required, save the final proposed plan as plan.json. Compute its digest from the exact file bytes, formatted as sha256:<64 lowercase hex characters>. For example, run python3 -c 'import hashlib, pathlib; print("sha256:" + hashlib.sha256(pathlib.Path("plan.json").read_bytes()).hexdigest())'. Record coordinator or human acceptance against that digest.
5. Create the executor packet and result, then the independent review result. Run the checker before each handoff:

   python3 scripts/check_handoff.py RUN_DIRECTORY --phase executor

   python3 scripts/check_handoff.py RUN_DIRECTORY --phase review

   python3 scripts/check_handoff.py RUN_DIRECTORY --phase integration

A successful check means the artifact contract permits the next handoff. It does not certify the plan’s quality or enforce that an agent is launched only after validation.

## Contract behavior

All artifacts set schema_version to 1.0. Unknown fields and unsupported versions fail validation. The checker confines referenced artifacts to the run directory and verifies raw-byte SHA-256 digests. run.json requires max_remediation_passes; the template sets it to one. The approval mode applies to plan acceptance. A review that requests changes allows another execution only while the current pass is below that limit. An escalation or exhausted limit blocks integration and exits with status 3 until a human records a resolution in the review result. A human may accept the risk for integration or keep it blocked.

Run the checks and tests with Python 3.11 or newer:

    python3 scripts/check_handoff.py templates/minimal-run --phase integration
    python3 -m unittest discover -s tests -v

The project adapter remains responsible for recording integration ownership and performing commits, merges, pushes, or deployment steps.

## Codex references

- [Codex skills](https://developers.openai.com/plugins/concepts/skills) describes skill folders with a SKILL.md and optional references, scripts, and templates.
- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) documents custom role profiles under .codex/agents/.

## License

MIT. See [LICENSE](LICENSE).
