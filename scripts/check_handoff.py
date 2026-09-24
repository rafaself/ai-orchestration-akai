#!/usr/bin/env python3
"""Validate orchestration handoffs without mutating the run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "v1"
SCHEMAS = {
    "run": "run.schema.json",
    "plan": "plan.schema.json",
    "acceptance": "plan-acceptance.schema.json",
    "packet": "executor-packet.schema.json",
    "execution": "executor-result.schema.json",
    "review": "review-result.schema.json",
    "integration": "integration-handoff.schema.json",
}


class GateError(Exception):
    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _actual_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _validate_schema_subset(value: Any, schema: dict[str, Any], location: str) -> None:
    """Validate the JSON Schema keywords used by the published v1 contracts."""
    expected_type = schema.get("type")
    if expected_type is not None:
        expected_types = expected_type if isinstance(expected_type, list) else [expected_type]
        actual_type = _actual_type(value)
        if actual_type not in expected_types and not (
            actual_type == "integer" and "number" in expected_types
        ):
            raise GateError(
                f"{location}: expected type {' or '.join(expected_types)}, got {actual_type}"
            )

    if "enum" in schema and value not in schema["enum"]:
        raise GateError(f"{location}: value is not one of the supported choices")

    if isinstance(value, dict):
        for required_key in schema.get("required", []):
            if required_key not in value:
                raise GateError(f"{location}: missing required field {required_key!r}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unexpected = sorted(set(value) - set(properties))
            if unexpected:
                raise GateError(
                    f"{location}: unsupported field(s): {', '.join(unexpected)}"
                )

        for key, child_schema in properties.items():
            if key in value:
                _validate_schema_subset(value[key], child_schema, f"{location}.{key}")

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        if minimum_items is not None and len(value) < minimum_items:
            raise GateError(
                f"{location}: expected at least {minimum_items} item(s), got {len(value)}"
            )
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                _validate_schema_subset(item, item_schema, f"{location}[{index}]")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if minimum_length is not None and len(value) < minimum_length:
            raise GateError(f"{location}: string must not be empty")
        pattern = schema.get("pattern")
        if pattern is not None and re.fullmatch(pattern, value) is None:
            raise GateError(f"{location}: string does not match the required format")

    if _actual_type(value) in {"integer", "number"}:
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            raise GateError(f"{location}: value must be at least {minimum}")


def _read_json(path: Path, description: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"{description} is missing: {path.name}") from exc
    except UnicodeDecodeError as exc:
        raise GateError(f"{description} is not valid UTF-8: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(
            f"{description} is malformed JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc


def _run_file(run_dir: Path, relative_path: str, description: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise GateError(f"{description} must be a relative path inside the run directory")

    try:
        resolved = (run_dir / candidate).resolve(strict=True)
    except FileNotFoundError as exc:
        raise GateError(f"{description} does not exist: {relative_path}") from exc

    if not resolved.is_relative_to(run_dir):
        raise GateError(f"{description} resolves outside the run directory")
    if not resolved.is_file():
        raise GateError(f"{description} is not a file: {relative_path}")
    return resolved


def _load_contract(run_dir: Path, relative_path: str, contract: str) -> tuple[Any, Path]:
    path = _run_file(run_dir, relative_path, contract)
    document = _read_json(path, contract)
    schema_path = SCHEMA_DIR / SCHEMAS[contract]
    schema = _read_json(schema_path, f"{contract} schema")
    if not isinstance(document, (dict, list)):
        raise GateError(f"{contract} must contain a JSON object or array")
    _validate_schema_subset(document, schema, relative_path)
    return document, path


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require_equal(actual: Any, expected: Any, description: str) -> None:
    if actual != expected:
        raise GateError(f"{description} does not match")


def _check_run_directory(path: Path) -> Path:
    try:
        run_dir = path.resolve(strict=True)
    except FileNotFoundError as exc:
        raise GateError(f"run directory does not exist: {path}") from exc
    if not run_dir.is_dir():
        raise GateError(f"run path is not a directory: {path}")
    return run_dir


def _executor_context(run_dir: Path) -> dict[str, Any]:
    run, _ = _load_contract(run_dir, "run.json", "run")
    packet, _ = _load_contract(run_dir, "executor-packet.json", "packet")

    _require_equal(packet["run_id"], run["run_id"], "executor packet run_id")
    decision = run["planning"]["decision"]
    _require_equal(packet["planning_decision"], decision, "planning decision")

    remediation_pass = packet["remediation_pass"]
    maximum = run["max_remediation_passes"]
    if remediation_pass > maximum:
        raise GateError(
            f"remediation pass {remediation_pass} exceeds the configured limit {maximum}; "
            "escalate unresolved findings",
            3,
        )

    plan = None
    plan_path = None
    plan_digest = None
    if decision == "required":
        if "skip_rationale" in packet:
            raise GateError("executor packet cannot contain skip_rationale when planning is required")
        plan_ref = packet.get("plan_ref")
        if plan_ref is None:
            raise GateError("planning is required but the executor packet has no plan reference")

        plan, plan_path = _load_contract(run_dir, plan_ref["path"], "plan")
        _require_equal(plan["run_id"], run["run_id"], "plan run_id")
        plan_digest = _digest(plan_path)
        _require_equal(plan_ref["sha256"], plan_digest, "executor packet plan digest")

        if plan.get("requires_human_approval") and not plan.get("escalation_reason"):
            raise GateError("plan requires human approval but has no escalation_reason")

        acceptance, _ = _load_contract(run_dir, "plan-acceptance.json", "acceptance")
        _require_equal(acceptance["run_id"], run["run_id"], "plan acceptance run_id")
        _require_equal(acceptance["plan_id"], plan["plan_id"], "plan acceptance plan_id")
        _require_equal(acceptance["plan_sha256"], plan_digest, "plan acceptance digest")

        if acceptance["decision"] == "escalate":
            raise GateError("plan acceptance escalated; human/coordinator resolution is required", 3)
        if acceptance["decision"] != "accepted":
            raise GateError("plan acceptance is not accepted; update the plan before execution")

        human_required = (
            run["approval"]["mode"] == "human"
            or plan["requires_human_approval"]
        )
        if human_required and acceptance["approver_role"] != "human":
            raise GateError("this plan requires recorded human approval")
    else:
        run_rationale = run["planning"].get("rationale", "").strip()
        packet_rationale = packet.get("skip_rationale", "").strip()
        if not run_rationale or not packet_rationale:
            raise GateError("a skipped planning decision requires a non-empty rationale")
        _require_equal(packet_rationale, run_rationale, "planning skip rationale")
        if "plan_ref" in packet:
            raise GateError("executor packet must omit plan_ref when planning is skipped")

    return {
        "run": run,
        "packet": packet,
        "plan": plan,
        "plan_digest": plan_digest,
        "plan_path": plan_path,
        "remediation_pass": remediation_pass,
    }


def _validate_execution_result(run_dir: Path, context: dict[str, Any]) -> tuple[Any, Path]:
    execution, execution_path = _load_contract(
        run_dir, "executor-result.json", "execution"
    )
    run = context["run"]
    _require_equal(execution["run_id"], run["run_id"], "executor result run_id")
    _require_equal(
        execution["plan_sha256"], context["plan_digest"], "executor result plan digest"
    )
    _require_equal(
        execution["remediation_pass"],
        context["remediation_pass"],
        "executor result remediation_pass",
    )

    plan = context["plan"]
    step_results = execution["step_results"]
    if plan is None:
        if step_results:
            raise GateError("executor result cannot map plan steps when planning was skipped")
    else:
        expected_ids = [step["step_id"] for step in plan["steps"]]
        actual_ids = [result["step_id"] for result in step_results]
        if len(actual_ids) != len(set(actual_ids)):
            raise GateError("executor result contains duplicate step IDs")
        if set(actual_ids) != set(expected_ids) or len(actual_ids) != len(expected_ids):
            raise GateError("executor result must map every plan step exactly once")

    return execution, execution_path


def _validate_review(run_dir: Path) -> tuple[str, dict[str, Any]]:
    context = _executor_context(run_dir)
    _, execution_path = _validate_execution_result(run_dir, context)
    review, _ = _load_contract(run_dir, "review-result.json", "review")

    run = context["run"]
    _require_equal(review["run_id"], run["run_id"], "review result run_id")
    _require_equal(
        review["plan_sha256"], context["plan_digest"], "review result plan digest"
    )
    _require_equal(
        review["executor_result_sha256"],
        _digest(execution_path),
        "review result executor-result digest",
    )
    _require_equal(
        review["remediation_pass"],
        context["remediation_pass"],
        "review result remediation_pass",
    )

    if review["outcome"] in {"changes_requested", "escalate"} and not review["findings"]:
        raise GateError("a changes_requested or escalate review must include findings")

    resolution = review.get("human_resolution")
    if review["outcome"] == "accepted":
        if resolution is not None:
            raise GateError("human_resolution is only valid for an escalated or exhausted review")
        return "accepted", context

    if resolution is not None:
        if resolution["decision"] == "blocked":
            raise GateError("human resolution blocked further work; route to the project decision owner", 3)
        if review["outcome"] == "escalate":
            return "accepted", context
        if context["remediation_pass"] >= run["max_remediation_passes"]:
            return "accepted", context
        raise GateError("human_resolution is only valid after escalation or remediation exhaustion")

    if review["outcome"] == "escalate":
        raise GateError(
            "reviewer escalated unresolved findings; recorded human resolution is required",
            3,
        )

    if context["remediation_pass"] >= run["max_remediation_passes"]:
        raise GateError(
            "remediation limit reached with unresolved review findings; escalate for human resolution",
            3,
        )
    return "remediation_allowed", context


def check_phase(run_dir: Path, phase: str) -> tuple[str, str]:
    if phase == "executor":
        _executor_context(run_dir)
        return "ready", "READY_FOR_EXECUTION: packet, plan binding, and approval are valid"

    review_state, context = _validate_review(run_dir)
    if phase == "review":
        if review_state == "remediation_allowed":
            return (
                review_state,
                "REMEDIATION_ALLOWED: create the next executor packet with an incremented pass",
            )
        return "accepted", "READY_FOR_INTEGRATION: review accepted"

    if phase == "integration":
        if review_state != "accepted":
            raise GateError("integration is blocked until review is accepted")

        integration, _ = _load_contract(
            run_dir, "integration-handoff.json", "integration"
        )
        _, execution_path = _validate_execution_result(run_dir, context)
        _, review_path = _load_contract(run_dir, "review-result.json", "review")

        _require_equal(integration["run_id"], context["run"]["run_id"], "integration run_id")
        _require_equal(
            integration["plan_sha256"], context["plan_digest"], "integration plan digest"
        )
        _require_equal(
            integration["executor_result_sha256"],
            _digest(execution_path),
            "integration executor-result digest",
        )
        _require_equal(
            integration["review_result_sha256"],
            _digest(review_path),
            "integration review-result digest",
        )
        _require_equal(
            integration["integration_policy_ref"],
            context["run"]["integration_policy_ref"],
            "integration policy reference",
        )
        return "ready", "READY_FOR_INTEGRATION_HANDOFF: evidence is consistent"

    raise GateError(f"unsupported phase: {phase}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a plan-execute-review handoff without changing files."
    )
    parser.add_argument("run_directory", type=Path, help="directory containing v1 run artifacts")
    parser.add_argument(
        "--phase",
        required=True,
        choices=("executor", "review", "integration"),
        help="handoff to validate",
    )
    args = parser.parse_args(argv)

    try:
        run_dir = _check_run_directory(args.run_directory)
        _, message = check_phase(run_dir, args.phase)
    except GateError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return exc.exit_code

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
