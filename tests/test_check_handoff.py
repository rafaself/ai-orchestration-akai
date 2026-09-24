from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_handoff.py"
EXAMPLE = ROOT / "templates" / "minimal-run"


def read_json(directory: Path, name: str):
    return json.loads((directory / name).read_text(encoding="utf-8"))


def write_json(directory: Path, name: str, document) -> None:
    (directory / name).write_text(
        json.dumps(document, indent=2) + "\n",
        encoding="utf-8",
    )


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_digests(directory: Path) -> None:
    run = read_json(directory, "run.json")
    packet = read_json(directory, "executor-packet.json")
    execution = read_json(directory, "executor-result.json")
    review = read_json(directory, "review-result.json")
    integration = read_json(directory, "integration-handoff.json")

    if run["planning"]["decision"] == "required":
        plan_sha = file_digest(directory / packet["plan_ref"]["path"])
        packet["plan_ref"]["sha256"] = plan_sha
        acceptance = read_json(directory, "plan-acceptance.json")
        acceptance["plan_sha256"] = plan_sha
        write_json(directory, "plan-acceptance.json", acceptance)
    else:
        plan_sha = None

    execution["plan_sha256"] = plan_sha
    review["plan_sha256"] = plan_sha
    integration["plan_sha256"] = plan_sha
    write_json(directory, "executor-packet.json", packet)
    write_json(directory, "executor-result.json", execution)
    review["executor_result_sha256"] = file_digest(directory / "executor-result.json")
    integration["executor_result_sha256"] = review["executor_result_sha256"]
    write_json(directory, "review-result.json", review)
    integration["review_result_sha256"] = file_digest(directory / "review-result.json")
    write_json(directory, "integration-handoff.json", integration)


class HandoffCheckerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temp_dir.name) / "run"
        shutil.copytree(EXAMPLE, self.run_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def invoke(self, phase: str, directory: Path | None = None):
        return subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                str(directory or self.run_dir),
                "--phase",
                phase,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_complete_happy_path_passes_every_phase(self):
        for phase in ("executor", "review", "integration"):
            with self.subTest(phase=phase):
                result = self.invoke(phase)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("READY_FOR_INTEGRATION_HANDOFF", self.invoke("integration").stdout)

    def test_missing_plan_fails_closed(self):
        (self.run_dir / "plan.json").unlink()
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)

    def test_missing_acceptance_fails_closed(self):
        (self.run_dir / "plan-acceptance.json").unlink()
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not exist", result.stderr)

    def test_mismatched_plan_digest_fails_closed(self):
        packet = read_json(self.run_dir, "executor-packet.json")
        packet["plan_ref"]["sha256"] = "sha256:" + "0" * 64
        write_json(self.run_dir, "executor-packet.json", packet)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("digest does not match", result.stderr)

    def test_unsupported_schema_version_fails_closed(self):
        run = read_json(self.run_dir, "run.json")
        run["schema_version"] = "2.0"
        write_json(self.run_dir, "run.json", run)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("supported choices", result.stderr)

    def test_human_policy_requires_human_acceptance(self):
        run = read_json(self.run_dir, "run.json")
        run["approval"]["mode"] = "human"
        write_json(self.run_dir, "run.json", run)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires recorded human approval", result.stderr)

    def test_human_policy_accepts_recorded_human_approval(self):
        run = read_json(self.run_dir, "run.json")
        run["approval"]["mode"] = "human"
        write_json(self.run_dir, "run.json", run)
        acceptance = read_json(self.run_dir, "plan-acceptance.json")
        acceptance["approver_role"] = "human"
        write_json(self.run_dir, "plan-acceptance.json", acceptance)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_plan_acceptance_id_must_match_plan(self):
        acceptance = read_json(self.run_dir, "plan-acceptance.json")
        acceptance["plan_id"] = "different-plan"
        write_json(self.run_dir, "plan-acceptance.json", acceptance)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("plan_id does not match", result.stderr)

    def test_plan_escalation_requires_human_acceptance(self):
        plan = read_json(self.run_dir, "plan.json")
        plan["requires_human_approval"] = True
        plan["escalation_reason"] = "A project owner must approve this risk."
        write_json(self.run_dir, "plan.json", plan)
        refresh_digests(self.run_dir)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires recorded human approval", result.stderr)

    def test_out_of_directory_plan_reference_is_rejected(self):
        outside = self.run_dir.parent / "outside-plan.json"
        shutil.copyfile(self.run_dir / "plan.json", outside)
        packet = read_json(self.run_dir, "executor-packet.json")
        packet["plan_ref"]["path"] = "../outside-plan.json"
        packet["plan_ref"]["sha256"] = file_digest(outside)
        write_json(self.run_dir, "executor-packet.json", packet)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside the run directory", result.stderr)

    def test_plan_step_mapping_must_be_exact(self):
        execution = read_json(self.run_dir, "executor-result.json")
        execution["step_results"].append(execution["step_results"][0])
        write_json(self.run_dir, "executor-result.json", execution)
        refresh_digests(self.run_dir)
        result = self.invoke("review")
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate step IDs", result.stderr)

    def test_skipped_planning_with_matching_reason_passes(self):
        run = read_json(self.run_dir, "run.json")
        run["planning"] = {
            "decision": "skipped",
            "rationale": "The task is limited to a copy-only documentation update."
        }
        write_json(self.run_dir, "run.json", run)

        packet = read_json(self.run_dir, "executor-packet.json")
        packet["planning_decision"] = "skipped"
        packet["skip_rationale"] = run["planning"]["rationale"]
        packet.pop("plan_ref")
        write_json(self.run_dir, "executor-packet.json", packet)

        (self.run_dir / "plan-acceptance.json").unlink()
        execution = read_json(self.run_dir, "executor-result.json")
        execution["step_results"] = []
        write_json(self.run_dir, "executor-result.json", execution)
        refresh_digests(self.run_dir)

        for phase in ("executor", "review", "integration"):
            with self.subTest(phase=phase):
                result = self.invoke(phase)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_skipped_planning_without_matching_reason_fails(self):
        run = read_json(self.run_dir, "run.json")
        run["planning"] = {"decision": "skipped", "rationale": "Not complex."}
        write_json(self.run_dir, "run.json", run)
        packet = read_json(self.run_dir, "executor-packet.json")
        packet["planning_decision"] = "skipped"
        packet["skip_rationale"] = "No rationale."
        packet.pop("plan_ref")
        write_json(self.run_dir, "executor-packet.json", packet)

        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("rationale does not match", result.stderr)

    def test_remediation_is_allowed_until_configured_limit_then_escalates(self):
        run = read_json(self.run_dir, "run.json")
        run["max_remediation_passes"] = 2
        write_json(self.run_dir, "run.json", run)
        review = read_json(self.run_dir, "review-result.json")
        review["outcome"] = "changes_requested"
        review["findings"] = [
            {
                "finding_id": "finding-1",
                "severity": "medium",
                "summary": "Add evidence for the second plan step.",
                "evidence": "The executor result has no direct validation reference."
            }
        ]
        write_json(self.run_dir, "review-result.json", review)
        refresh_digests(self.run_dir)

        result = self.invoke("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REMEDIATION_ALLOWED", result.stdout)

        packet = read_json(self.run_dir, "executor-packet.json")
        execution = read_json(self.run_dir, "executor-result.json")
        review = read_json(self.run_dir, "review-result.json")
        packet["remediation_pass"] = 1
        execution["remediation_pass"] = 1
        review["remediation_pass"] = 1
        write_json(self.run_dir, "executor-packet.json", packet)
        write_json(self.run_dir, "executor-result.json", execution)
        write_json(self.run_dir, "review-result.json", review)
        refresh_digests(self.run_dir)

        result = self.invoke("review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REMEDIATION_ALLOWED", result.stdout)

        packet = read_json(self.run_dir, "executor-packet.json")
        execution = read_json(self.run_dir, "executor-result.json")
        review = read_json(self.run_dir, "review-result.json")
        packet["remediation_pass"] = 2
        execution["remediation_pass"] = 2
        review["remediation_pass"] = 2
        write_json(self.run_dir, "executor-packet.json", packet)
        write_json(self.run_dir, "executor-result.json", execution)
        write_json(self.run_dir, "review-result.json", review)
        refresh_digests(self.run_dir)

        result = self.invoke("review")
        self.assertEqual(result.returncode, 3)
        self.assertIn("escalate", result.stderr)

    def test_escalated_review_blocks_integration(self):
        review = read_json(self.run_dir, "review-result.json")
        review["outcome"] = "escalate"
        review["findings"] = [
            {
                "finding_id": "risk-1",
                "severity": "high",
                "summary": "A human decision is required.",
                "evidence": "The project policy requires human approval."
            }
        ]
        write_json(self.run_dir, "review-result.json", review)
        refresh_digests(self.run_dir)
        result = self.invoke("integration")
        self.assertEqual(result.returncode, 3)
        self.assertIn("human resolution is required", result.stderr)

    def test_stale_integration_review_digest_is_rejected(self):
        integration = read_json(self.run_dir, "integration-handoff.json")
        integration["review_result_sha256"] = "sha256:" + "0" * 64
        write_json(self.run_dir, "integration-handoff.json", integration)
        result = self.invoke("integration")
        self.assertEqual(result.returncode, 1)
        self.assertIn("review-result digest does not match", result.stderr)

    def test_malformed_run_json_fails_closed(self):
        (self.run_dir / "run.json").write_text("{broken", encoding="utf-8")
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("malformed JSON", result.stderr)

    def test_plan_run_id_must_match_run_policy(self):
        plan = read_json(self.run_dir, "plan.json")
        plan["run_id"] = "different-run"
        write_json(self.run_dir, "plan.json", plan)
        refresh_digests(self.run_dir)
        result = self.invoke("executor")
        self.assertEqual(result.returncode, 1)
        self.assertIn("plan run_id does not match", result.stderr)

    def test_review_escalation_can_continue_after_human_acceptance(self):
        review = read_json(self.run_dir, "review-result.json")
        review["outcome"] = "escalate"
        review["findings"] = [
            {
                "finding_id": "risk-2",
                "severity": "high",
                "summary": "A human decision is required.",
                "evidence": "The project adapter marks this change as an escalation."
            }
        ]
        review["human_resolution"] = {
            "approver_role": "human",
            "decision": "accepted",
            "notes": "The project owner reviewed the risk and approved integration."
        }
        write_json(self.run_dir, "review-result.json", review)
        refresh_digests(self.run_dir)
        for phase in ("review", "integration"):
            with self.subTest(phase=phase):
                result = self.invoke(phase)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_checker_does_not_mutate_run_artifacts(self):
        before = {
            path.name: path.read_bytes()
            for path in self.run_dir.iterdir()
            if path.is_file()
        }
        for phase in ("executor", "review", "integration"):
            result = self.invoke(phase)
            self.assertEqual(result.returncode, 0, result.stderr)
        after = {
            path.name: path.read_bytes()
            for path in self.run_dir.iterdir()
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_codex_profiles_define_all_roles_and_sandbox_modes(self):
        profiles = {
            "planner.toml": "read-only",
            "executor.toml": "workspace-write",
            "reviewer.toml": "read-only",
        }
        for filename, expected_mode in profiles.items():
            with self.subTest(profile=filename):
                config = tomllib.loads(
                    (ROOT / ".codex" / "agents" / filename).read_text(encoding="utf-8")
                )
                self.assertTrue(config["name"])
                self.assertTrue(config["description"])
                self.assertTrue(config["developer_instructions"])
                self.assertEqual(config["sandbox_mode"], expected_mode)

    def test_every_contract_schema_and_template_is_valid_json(self):
        schema_files = sorted((ROOT / "contracts" / "v1").glob("*.schema.json"))
        self.assertEqual(len(schema_files), 7)
        for path in schema_files:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))
        for path in EXAMPLE.glob("*.json"):
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
