# Adapt the workflow to a project

Do not copy these files into a project and assume the defaults fit. Before enabling the skill or agent profiles:

- Read the project’s AGENTS.md, architecture guidance, security rules, data handling requirements, and current development workflow.
- Decide which tasks require a plan and who may accept it. Keep coordinator acceptance as the default only when the project’s governance permits it. Require human approval for the project’s escalations or other designated risk decisions.
- Set remediation limits to match the project’s review and release practices.
- Define the executor’s writable scope, available tools, required validations, and any rules for dependencies, tests, or generated files.
- Define which role may commit, merge, push, deploy, or perform other external changes. The generic kit grants none of those permissions.
- Decide who owns integration and where accepted handoff evidence belongs. Store a reference to that policy in run.json and the integration handoff.
- Remove example model names or sandbox settings that are not supported or appropriate in the target environment.

The checker validates structural and cross-file consistency. It cannot validate authorization policy, assess semantic plan quality, or guarantee that users follow a gated transition. Keep those decisions in the project’s maintained instructions and controls.
