# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Architecture boundary tests for the Python application layers."""

from __future__ import annotations

import ast
import hashlib
import importlib
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_BLUEPRINT_DIR = _REPO_ROOT / "app" / "blueprints"
_API_V1_SERVICE_DIR = _REPO_ROOT / "app" / "services" / "api_v1"
_API_V1_SERVICE_ALLOWED_FILES = {
    "__init__.py",
    "auth.py",
    "openapi.py",
    "openapi_assessment_action_artifact.py",
    "openapi_assessment_action_nuclei.py",
    "openapi_nuclei_template_snapshot.py",
    "openapi_assessment_action_profile.py",
    "openapi_assessment_action_schemas.py",
    "openapi_atlas_profile.py",
    "openapi_assessment_actions.py",
    "openapi_assessment_deltas.py",
    "openapi_assessment_evidence.py",
    "openapi_assessment_oast.py",
    "openapi_assessment_retests.py",
    "openapi_assessment_worklist.py",
    "openapi_assessment_zap.py",
    "openapi_assessments.py",
    "openapi_cve_advisory.py",
    "openapi_cve_risk.py",
    "openapi_finding_details.py",
    "openapi_finding_dispositions.py",
    "openapi_finding_evidence.py",
    "openapi_http_profiles.py",
    "openapi_finding_verification.py",
    "openapi_finding_verification_suggestion.py",
    "openapi_findings.py",
    "openapi_manual_findings.py",
    "openapi_osv_lookup.py",
    "openapi_probe_examples.py",
    "openapi_probe_schemas.py",
    "openapi_probes.py",
    "openapi_finding_priority.py",
    "openapi_run_evidence.py",
    "openapi_verification_actions.py",
    "serialization.py",
}

_DIRECT_TEAM_RUN_PREDICATE_RE = re.compile(
    r"\b(?:runs|r)\.session_id\s*=\s*\?.{0,240}\b(?:runs|r)\.team_id\s*=\s*\?"
    r"|\b(?:runs|r)\.team_id\s*=\s*\?.{0,240}\b(?:runs|r)\.session_id\s*=\s*\?",
    re.IGNORECASE | re.DOTALL,
)
_UNQUALIFIED_TEAM_RUN_PREDICATE_RE = re.compile(
    r"\bsession_id\s*=\s*\?.{0,240}\bteam_id\s*=\s*\?"
    r"|\bteam_id\s*=\s*\?.{0,240}\bsession_id\s*=\s*\?",
    re.IGNORECASE | re.DOTALL,
)
_RUN_SQL_RE = re.compile(r"\b(?:FROM|JOIN)\s+runs\b|\bruns\.", re.IGNORECASE)


def _stringish_source(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
            else "{}"
            for part in node.values
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _stringish_source(node.left) + _stringish_source(node.right)
    return ""


def _assignment_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _team_scope_sql_fragments(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    fragments: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            target_names = {_assignment_name(target) for target in node.targets}
            if any(
                name.endswith(("_sql", "_query", "_clause"))
                or name in {"sql", "query"}
                for name in target_names
            ):
                source = _stringish_source(node.value)
                if source:
                    fragments.append((node.lineno, source))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"execute", "executemany"}
            and node.args
        ):
            source = _stringish_source(node.args[0])
            if source:
                fragments.append((node.lineno, source))
    return fragments


@dataclass(frozen=True)
class BlueprintPersistenceMetrics:
    connection_calls: int = 0
    connection_symbols: int = 0
    execute_calls: int = 0
    core_database_symbols: int = 0
    core_database_backend_symbols: int = 0
    cleanup_helper_symbols: int = 0
    sql_string_fragments: int = 0

    def nonzero(self) -> bool:
        return any(getattr(self, field) for field in self.__dataclass_fields__)


_PERSISTENCE_CLEANUP_HELPERS = {
    "delete_run_artifacts",
    "delete_snapshot_metadata",
}

_PERSISTENCE_EXECUTE_METHODS = {
    "execute",
    "executemany",
    "executescript",
}

_PERSISTENCE_CONNECTION_SYMBOLS = {
    "db_connect",
}

_BLUEPRINT_PERSISTENCE_RATCHET = {}


@dataclass(frozen=True)
class ModuleSizeBudget:
    path: str
    max_lines: int
    treatment: str


_MODULE_SIZE_RATCHET = (
    ModuleSizeBudget("app/services/connectors/oast_correlations.py", 284, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/oast_correlation_lifecycle.py", 174, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/oast_config.py", 75, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/connectors/oast_interaction_findings.py", 113, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_interaction_review.py", 241, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/connectors/oast_interactions.py", 338, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/connectors/oast_provider_contracts.py", 38, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_provider_crypto.py", 131, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_provider_http.py", 134, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_provider_normalization.py", 93, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_provider_spool.py", 313, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_provider_transport.py", 189, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/connectors/oast_worker.py", 291, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/connectors/oast_worker_ingestion.py", 76, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_worker_lock.py", 56, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/oast_worker_state.py", 97, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/connectors/zap_config.py", 127, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_http.py", 172, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_job_artifacts.py", 195, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_job_lifecycle.py", 271, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_job_queue.py", 57, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_jobs.py", 288, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/connectors/zap_observability.py", 104, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/connectors/zap_plan.py", 205, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_plan_contracts.py", 54, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_plan_scope.py", 165, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_remote_progress.py", 154, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_scope.py", 121, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_scope_policy.py", 263, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_transport.py", 174, "split-package-ratchet"),
    ModuleSizeBudget("app/services/connectors/zap_worker.py", 361, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/connectors/zap_worker_observability.py", 65, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/connectors/zap_worker_lock.py", 53, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/connectors/zap_worker_support.py", 67, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/connectors/zap_worker_telemetry.py", 214, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/commands/registry.py", 1150, "split-target-phase1"),
    ModuleSizeBudget("app/services/commands/registry_adaptations.py", 87, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_autocomplete.py", 564, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_cache.py", 104, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_catalog.py", 359, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_content.py", 565, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_assessment_workflows.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_service_workflows.py", 77, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_subdomain_workflows.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_web_review_workflows.py", 53, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_faq.py", 505, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_loader.py", 744, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_semantics.py", 39, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_sqlmap.py", 77, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_runtime.py", 173, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_secret_specs.py", 157, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_smoke.py", 199, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_targets.py", 345, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_trufflehog.py", 70, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_validate.py", 178, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_validation.py", 239, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/registry_workspace.py", 466, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/run.py", 799, "split-target-phase2"),
    ModuleSizeBudget("app/blueprints/run_broker.py", 149, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/run_client.py", 153, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/run_kill.py", 123, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/run_pty.py", 259, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/run_support.py", 119, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects.py", 577, "split-target-phase3"),
    ModuleSizeBudget("app/blueprints/projects_assessment_action_launch.py", 187, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_assessment_actions.py", 162, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_assessment_checks.py", 238, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_assessment_oast.py", 165, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/blueprints/projects_assessment_oast_launch.py", 221, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/blueprints/projects_assessment_zap.py", 207, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_assessments.py", 300, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_artifacts.py", 155, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_auto_promote.py", 204, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_core.py", 412, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_findings.py", 272, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_finding_evidence.py", 146, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_finding_triage.py", 142, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_http_profiles.py", 214, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_manual_findings.py", 165, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_finding_merges.py", 145, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_retest_queue.py", 165, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_links.py", 242, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_metadata.py", 158, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_monitoring.py", 239, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_monitoring_risk.py", 65, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_packages.py", 386, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_probes.py", 84, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_probe_launch.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_probe_targets.py", 40, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/probe_log_context.py", 16, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_report.py", 301, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_targets.py", 111, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_verification_actions.py", 169, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/projects_web_surface.py", 21, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1.py", 795, "split-target-phase3"),
    ModuleSizeBudget("app/blueprints/api_v1_assessment_action_launch.py", 186, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_assessment_actions.py", 167, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_assessment_checks.py", 267, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_assessment_oast.py", 169, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/blueprints/api_v1_assessment_oast_launch.py", 220, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/blueprints/api_v1_assessment_zap.py", 217, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_assessments.py", 359, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_atlas_lookup.py", 27, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_atlas_profile.py", 33, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_finding_evidence.py", 167, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_http_profiles.py", 253, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_manual_findings.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_notifications.py", 159, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_osv_lookup.py", 114, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_probe_launch.py", 170, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_probe_targets.py", 50, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_probes.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_read.py", 401, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_run_evidence.py", 24, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_runs.py", 340, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_schedules.py", 211, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_streaming.py", 150, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_teams.py", 354, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_verification_actions.py", 168, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/api_v1_watchers.py", 240, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/atlas.py", 685, "split-target-phase3"),
    ModuleSizeBudget("app/blueprints/atlas_intel_refresh.py", 54, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/atlas_lookup_read.py", 33, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/atlas_mutations.py", 680, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/atlas_profile_read.py", 38, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/atlas_read.py", 160, "split-package-ratchet"),
    ModuleSizeBudget("app/core/database.py", 1007, "already-resolved-ratchet"),
    ModuleSizeBudget("app/blueprints/history.py", 1417, "already-resolved-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi.py", 2564, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_assessment_action_profile.py", 49, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/api_v1/openapi_assessment_action_schemas.py",
        100,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/api_v1/openapi_assessment_action_artifact.py",
        60,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/api_v1/openapi_assessment_action_nuclei.py",
        37,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/api_v1/openapi_nuclei_template_snapshot.py",
        30,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/api_v1/openapi_assessment_actions.py", 89, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_assessment_deltas.py", 277, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/api_v1/openapi_assessment_evidence.py", 66, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/api_v1/openapi_assessment_retests.py",
        179,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/api_v1/openapi_assessment_worklist.py", 195, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_assessment_oast.py", 287, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_assessment_zap.py", 330, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_assessments.py", 729, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_cve_advisory.py", 66, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_cve_risk.py", 94, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_finding_details.py", 47, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_findings.py", 151, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_finding_evidence.py", 172, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_http_profiles.py", 251, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_finding_verification.py", 135, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_finding_verification_suggestion.py", 49, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_manual_findings.py", 157, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_osv_lookup.py", 86, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_run_evidence.py", 98, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_verification_actions.py", 209, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_finding_priority.py", 81, "split-package-ratchet"),
    ModuleSizeBudget("app/core/output_entities.py", 393, "split-package-ratchet"),
    ModuleSizeBudget("app/core/output_port_entities.py", 207, "split-package-ratchet"),
    ModuleSizeBudget("app/core/output_shodan.py", 74, "split-package-ratchet"),
    ModuleSizeBudget("app/core/output_signals.py", 1195, "split-target-phase4"),
    ModuleSizeBudget("app/core/output_structured_signals.py", 223, "split-package-ratchet"),
    ModuleSizeBudget("app/core/output_targets.py", 239, "split-package-ratchet"),
    ModuleSizeBudget("app/core/output_target_recon.py", 62, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/intel_profile.py", 93, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/intel_evidence.py", 335, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/intel_summary.py", 370, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_query.py", 68, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_resolve.py", 347, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup.py", 962, "split-target-phase4"),
    ModuleSizeBudget("app/services/atlas/lookup_export.py", 277, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_filters.py", 169, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_finding_fields.py", 48, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_metadata.py", 210, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_mutations.py", 122, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_runs.py", 200, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/lookup_search.py", 73, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/__init__.py", 4, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/action_plan_nuclei.py", 56, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/action_plan_oast.py", 67, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/action_plan_payload.py", 39, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/action_plans.py", 318, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/base_action_catalog.py", 129, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/dalfox_command_tokens.py", 29, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_plan_contracts.py", 12, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_target_urls.py", 22, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_modes.py", 83, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_modes_tls.py", 33, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_modes_dalfox.py", 83, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/command_modes_dalfox_oast.py",
        38,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/command_modes_nuclei.py", 73, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_plans.py", 112, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_plans_tls.py", 43, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/command_plans_web.py", 80, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/cyclonedx_component_document.py", 80, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/cyclonedx_cpe_observations.py", 110, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/cyclonedx_package_observations.py", 105, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/cyclonedx_stored_nvd.py", 60, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/cyclonedx_stored_osv.py", 70, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/contracts.py", 45, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/cleanup.py", 42, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/coverage.py", 261, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/deletion_preview.py", 70, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/evidence_matching.py", 346, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/evidence_target_parsing.py",
        75,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/evidence_read.py", 91, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/evidence_sources.py", 330, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/finding_worklist.py", 165, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/manual_evidence_read.py", 58, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/plan_confirmation.py", 64, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_catalog.py", 160, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/probe_catalog_recommendations.py",
        40,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/probe_confirmation.py", 35, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_execution.py", 75, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_log_context.py", 59, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_probe_examples.py", 123, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_probe_schemas.py", 370, "split-package-ratchet"),
    ModuleSizeBudget("app/services/api_v1/openapi_probes.py", 156, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_contracts.py", 78, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_plan_digest.py", 62, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_plans.py", 222, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_service.py", 106, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_targets.py", 118, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/http_profile_contracts.py", 34, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/httpx_version_observations.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/httpx_stored_nvd.py", 70, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/http_profile_execution.py", 349, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/http_profile_material.py", 163, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/http_profile_material_formats.py", 49, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/http_profile_target_scope.py",
        105,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/service_actions.py", 90, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/service_action_catalog.py", 130, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/service_action_recommendations.py",
        120,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/nmap_profiles.py", 80, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/nmap_profile_catalog.py",
        105,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/nmap_profile_contracts.py",
        25,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/nmap_exact_output_evidence.py",
        35,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/nmap_script_evidence_catalog.py",
        60,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/nmap_service_observations.py",
        215,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/nmap_service_evidence_persistence.py",
        165,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/nmap_service_evidence_read.py",
        154,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/osv_package_correlation.py", 220, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/http_profile_runtime.py", 175, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/http_profile_runtime_read.py", 166, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/http_profile_scope.py", 75, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/http_profile_secret_references.py",
        69,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/http_profile_validation.py", 362, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/export_context.py", 329, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/http_profiles.py", 550, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/handoff.py", 110, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/lifecycle.py", 376, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/mutations.py", 493, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/profile_summaries.py", 27, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/profiles.py", 686, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/assessments/read_model.py", 266, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/read_model_queries.py", 162, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_recommendation_evidence.py",
        230,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_recommendations.py",
        135,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/reconciliation.py", 469, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/reconciliation_cleanup.py", 63, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/reconciliation_observations.py", 120, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/reconciliation_read.py", 231, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/reconciliation_read_filters.py", 90, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/recommended_actions.py", 107, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/retest_finalization.py",
        104,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/retest_queue.py", 368, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/recommended_action_profiles.py", 35, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/recommended_action_queries.py", 41, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/schema.py", 10, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/serialization.py", 128, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/storage.py", 379, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/summary.py", 106, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/target_rollups.py", 32, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/zap_connector.py", 545, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/actors.py", 39, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/artifact_queries.py", 249, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/entity_monitoring.py", 139, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/finding_identity.py", 127, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/finding_evidence.py", 327, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/finding_evidence_sources.py", 232, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/verification_actions.py", 133, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/overview.py", 1081, "split-target-phase4"),
    ModuleSizeBudget("app/services/projects/overview_app.py", 452, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/overview_intel.py", 294, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/files.py", 1080, "split-target-phase4"),
    ModuleSizeBudget("app/services/workspace/file_mutations.py", 254, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/maintenance.py", 401, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/metadata.py", 172, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/modes.py", 6, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/models.py", 87, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/paths.py", 165, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/settings.py", 77, "split-package-ratchet"),
    ModuleSizeBudget("app/core/migrations/baseline.py", 1689, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/pty/runtime.py", 106, "split-package-ratchet"),
    ModuleSizeBudget("app/services/pty/service.py", 1191, "split-target-phase4"),
    ModuleSizeBudget("app/services/pty/settings.py", 95, "split-package-ratchet"),
    ModuleSizeBudget("app/services/pty/snapshots.py", 64, "split-package-ratchet"),
    ModuleSizeBudget("app/services/pty/state.py", 155, "split-package-ratchet"),
    ModuleSizeBudget("app/services/pty/wire.py", 96, "split-package-ratchet"),
    ModuleSizeBudget("app/services/history/insights.py", 305, "split-package-ratchet"),
    ModuleSizeBudget("app/services/history/mutations.py", 291, "split-package-ratchet"),
    ModuleSizeBudget("app/services/history/queries.py", 904, "split-target-phase4"),
    ModuleSizeBudget("app/services/history/retention.py", 88, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/package_queries.py", 71, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/list_queries.py", 256, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/list_metrics.py", 268, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/list_switcher.py", 138, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/queries.py", 777, "split-target-phase4"),
    ModuleSizeBudget("app/services/projects/web_surface.py", 169, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/web_surface_comparison.py", 151, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/web_surface_entities.py", 84, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/web_surface_history_query.py", 31, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/web_surface_query.py", 56, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_archive.py", 146, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_analysis.py", 265, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_counts.py", 47, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_draft_read.py", 127, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_evidence.py", 108, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_helpers.py", 131, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_limits.py", 150, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_logging.py", 48, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/nessus_versions.py", 118, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_types.py", 85, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_workflow.py", 972, "split-target-phase4"),
    ModuleSizeBudget("app/blueprints/assets.py", 403, "split-target-phase4"),
    ModuleSizeBudget("app/blueprints/assets_audit.py", 391, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/assets_diag.py", 657, "split-package-ratchet"),
    ModuleSizeBudget("app/core/process.py", 1170, "ratchet-only"),
    ModuleSizeBudget("app/services/metrics/__init__.py", 987, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/metrics/assessments.py", 340, "split-package-ratchet"),
    ModuleSizeBudget("app/services/metrics/probes.py", 64, "split-package-ratchet"),
    ModuleSizeBudget("app/services/projects/auto_promote.py", 963, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/runs/broker_worker.py", 496, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/broker_observability.py", 59, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/broker_batcher.py", 130, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/broker_capture.py", 46, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/completion_policy.py", 69, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/runs/completion_policy_contracts.py", 37, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/runs/schemathesis_completion.py", 45, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/runs/execution_override.py", 65, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/finalization.py", 1000, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/finalization_artifacts.py", 85, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/finalization_assessment_findings.py", 57, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/finalization_assessments.py", 77, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/runs/finalization_dalfox_xss.py", 75, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/runs/finalization_schemathesis.py", 120, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/runs/finalization_nmap_evidence.py", 64, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/runs/finalization_nmap_service_evidence.py",
        79,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/runs/finalization_nmap_xml.py", 79, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/runs/finalization_observability.py", 52, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/runs/finalization_summaries.py", 38, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/finalization_takeover.py", 70, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/finalization_version_inference.py", 160, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/finalization_web_surface.py", 140, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/runs/finalization_web_surface_query.py", 60, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/runs/finalization_web_surface_storage.py", 220, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/runs/httpx_workspace_artifact_metadata.py", 70, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/runs/lifecycle.py", 660, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/project_notices.py", 116, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/scope.py", 188, "split-package-ratchet"),
    ModuleSizeBudget("app/core/schema_manifest.py", 911, "cohesive-ratchet"),
    ModuleSizeBudget("app/core/database_backend.py", 845, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/commands/builtins_runtime.py", 824, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/builtins_runtime_specs.py", 169, "split-package-ratchet"),
    ModuleSizeBudget("app/services/commands/builtins_assessment.py", 140, "split-package-ratchet"),
    ModuleSizeBudget("app/blueprints/teams.py", 796, "ratchet-only"),
    ModuleSizeBudget("app/services/runs/postfilters.py", 368, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/output_sinks.py", 143, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/output_sink_files.py", 81, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/process_control.py", 85, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_formats.py", 20, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_parser.py", 870, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/atlas/sarif_parser.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/sarif_details.py", 255, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/cyclonedx_parser.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/cyclonedx_details.py", 308, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/takeover_detection.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/takeover_confirmation.py", 230, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/takeover_finding_evidence.py", 140, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/takeover_finding_materialization.py",
        110,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/takeover_finding_persistence.py",
        170,
        "split-package-ratchet",
    ),
    ModuleSizeBudget("app/services/assessments/nuclei_takeover_identity.py", 70, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_takeover_observations.py", 130, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_takeover_templates.py", 150, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_takeover_launch.py", 150, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_profile_launch.py", 70, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/probe_launch.py", 60, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_cleanup.py", 83, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/probe_log_classification.py", 39, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/probe_log_safety.py", 60, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_observability.py", 80, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/probe_observability_support.py", 77, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/probe_broker_launch.py", 61, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_http_profile_plans.py", 44, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_protected_launch.py", 47, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/probe_target_service.py", 20, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/probe_target_resolution.py", 96, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_takeover_contracts.py", 20, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/nuclei_takeover_command.py", 80, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/dns_takeover_context.py", 65, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/dns_takeover_correlation.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/dns_takeover_event_review.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/dns_takeover_identity.py", 60, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/dns_takeover_observations.py", 170, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/core/output_dnsx.py", 85, "split-package-ratchet"),
    ModuleSizeBudget("app/core/output_nuclei.py", 60, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/web_surface.py", 120, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/cpe_applicability.py", 158, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/versioned_cpe.py", 34, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/nessus_import_observations.py", 155, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/nessus_stored_nvd.py", 49, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/nessus_inference_materialization.py", 44, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/nvd_cpe_correlation.py", 186, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/nmap_stored_nvd.py", 60, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/nmap_inference_materialization.py", 55, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/httpx_inference_materialization.py", 55, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/nmap_version_observations.py", 180, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_parameter_observations.py", 173, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_parameter_evidence.py", 239, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_parameter_options.py", 160, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_actions.py", 114, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_contracts.py", 5, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_command.py", 99, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_oast_contracts.py", 14, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_oast_command.py", 126, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_oast_actions.py", 163, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_execution.py", 53, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_launch.py", 124, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_finding_materialization.py",
        220,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_finding_persistence.py",
        240,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_xss_observations.py", 346, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_schema.py", 269, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_command.py", 109, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_command_paths.py", 44, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_artifact.py", 106, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_material.py", 102, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_actions.py", 188, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_execution.py", 47, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_evidence_matching.py", 67, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_evidence_persistence.py",
        318,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_finding_persistence.py",
        204,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_launch.py", 122, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_launch_execution.py",
        33,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_report_context.py",
        45,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_report.py", 582, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_report_contracts.py",
        83,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/schemathesis_report_decode.py",
        154,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/recommended_action_selections.py",
        74,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/recommended_action_selection_contexts.py",
        92,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/assessment_oast.py",
        337,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/assessment_oast_launch_confirmation.py",
        193,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/assessment_oast_run_launch.py",
        143,
        "split-package-ratchet",
    ),
    ModuleSizeBudget(
        "app/services/assessments/dalfox_oast_execution.py", 50, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/run_launch.py", 105, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/run_launch_context.py", 26, "split-package-ratchet"
    ),
    ModuleSizeBudget(
        "app/services/assessments/recommended_action_builder.py", 77, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/stored_nvd_inference.py", 52, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/stored_osv_inference.py", 60, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/version_correlation.py", 150, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/version_finding_candidates.py", 105, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/version_inference_inputs.py", 100, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/version_inference_materialization.py", 65, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/version_inference_persistence.py", 185, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/assessments/version_inference_source_validation.py", 80, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/assessments/version_ranges.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/web_gallery.py", 140, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/collections.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout.py", 140, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_policy.py", 120, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_checkpoint.py", 150, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_summary.py", 120, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_children.py", 180, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_child_lifecycle.py", 260, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_child_queries.py", 50, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_child_failures.py", 140, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_child_cancellation.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_parent_completion.py", 120, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_launch.py", 170, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_child_run.py", 185, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/fanout_launch_state.py", 170, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workflows/transitions.py", 80, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/nuclei_profiles.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/services/nuclei/template_cache.py", 170, "split-package-ratchet"),
    ModuleSizeBudget("app/services/assessments/historical_urls.py", 140, "split-package-ratchet"),
    ModuleSizeBudget("app/services/intel/epss.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/services/intel/kev.py", 110, "split-package-ratchet"),
    ModuleSizeBudget("app/services/intel/cpe.py", 31, "split-package-ratchet"),
    ModuleSizeBudget("app/services/intel/nvd_applicability.py", 169, "split-package-ratchet"),
    ModuleSizeBudget("app/services/cve_risk/nvd_applicability_store.py", 100, "split-package-ratchet"),
    ModuleSizeBudget("app/services/cve_risk/osv_acquisition.py", 141, "split-package-ratchet"),
    ModuleSizeBudget("app/services/cve_risk/osv_external.py", 200, "split-package-ratchet"),
    ModuleSizeBudget("app/services/cve_risk/osv_external_http.py", 131, "split-package-ratchet"),
    ModuleSizeBudget("app/services/cve_risk/osv_external_store.py", 169, "split-package-ratchet"),
    ModuleSizeBudget("app/services/cve_risk/osv_parser.py", 267, "split-package-ratchet"),
    ModuleSizeBudget("app/services/cve_risk/osv_store.py", 210, "split-package-ratchet"),
    ModuleSizeBudget("app/services/atlas/import_sources.py", 226, "split-package-ratchet"),
    ModuleSizeBudget("app/services/pty/__init__.py", 0, "split-package-ratchet"),
    ModuleSizeBudget("app/services/pty/capture.py", 422, "split-package-ratchet"),
    ModuleSizeBudget("app/services/pty/transcript.py", 73, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/__init__.py", 0, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/broker.py", 716, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/comparison.py", 1263, "cohesive-ratchet"),
    ModuleSizeBudget("app/services/runs/comparison_derived.py", 204, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/comparison_findings.py", 238, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/contracts.py", 41, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/kinds.py", 53, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/output_model.py", 534, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/output_store.py", 423, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/persistence.py", 161, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/private_data.py", 246, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/start.py", 219, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/start_context.py", 63, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/start_contracts.py", 30, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/signal_context.py", 57, "split-package-ratchet"),
    ModuleSizeBudget(
        "app/services/runs/schemathesis_execution_override.py", 29, "split-package-ratchet"
    ),
    ModuleSizeBudget("app/services/runs/streaming.py", 156, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/structured_filters.py", 317, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/structured_summary.py", 59, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/workspace_artifact_metadata.py", 81, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/workspace_artifacts.py", 92, "split-package-ratchet"),
    ModuleSizeBudget("app/services/runs/worker_cleanup.py", 37, "split-package-ratchet"),
    ModuleSizeBudget("app/services/workspace/__init__.py", 0, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/__init__.py", 5, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/__main__.py", 2102, "split-target-phase4"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/client.py", 336, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/formatting.py", 86, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/commands/__init__.py", 1, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/commands/assessment.py", 116, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/commands/probe.py", 133, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/commands/probe_catalog_formatting.py", 59, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/commands/probe_formatting.py", 71, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/parsers/__init__.py", 1, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/parsers/assessment.py", 81, "split-package-ratchet"),
    ModuleSizeBudget("tools/darklab_cli/src/darklab_cli/parsers/probe.py", 44, "split-package-ratchet"),
)

_MODULE_SIZE_RATCHET_REQUIRED_PATTERNS = (
    "app/blueprints/api_v1*.py",
    "app/blueprints/projects*.py",
    "app/blueprints/run*.py",
    "app/blueprints/atlas*.py",
    "app/blueprints/assets*.py",
    "app/core/output*.py",
    "app/services/commands/registry*.py",
    "app/services/runs/*.py",
    "app/services/pty/*.py",
    "app/services/workspace/*.py",
    "app/services/history/insights.py",
    "app/services/history/mutations.py",
    "app/services/history/queries.py",
    "app/services/history/retention.py",
    "app/services/atlas/import*.py",
    "app/services/atlas/intel_summary.py",
    "app/services/atlas/lookup*.py",
    "app/services/assessments/*.py",
    "app/services/projects/actors.py",
    "app/services/projects/artifact_queries.py",
    "app/services/projects/list*.py",
    "app/services/projects/overview*.py",
    "app/services/projects/package_queries.py",
    "app/services/projects/queries.py",
    "tools/darklab_cli/src/darklab_cli/*.py",
    "tools/darklab_cli/src/darklab_cli/commands/*.py",
    "tools/darklab_cli/src/darklab_cli/parsers/*.py",
)

_DECOMPOSED_ROUTE_BLUEPRINTS = frozenset({"api_v1", "run", "projects", "atlas", "assets"})
_DECOMPOSED_ROUTE_CONTRACT_COUNT = 272
_DECOMPOSED_ROUTE_CONTRACT_SHA256 = "c8ff033290e3d9976dd820fb56a0e68b706b74e1180d3c9824a8760931d44cfa"

_PUBLIC_IMPORT_COMPATIBILITY_CONTRACT = (
    ("blueprints.api_v1", "api_health", "callable"),
    ("blueprints.api_v1", "api_runs_start", "callable"),
    ("blueprints.api_v1", "_sse_after_id", "callable"),
    ("blueprints.projects", "projects_list", "callable"),
    ("blueprints.projects", "projects_create", "callable"),
    ("blueprints.projects", "get_project_intel_overview", "callable"),
    ("blueprints.run", "start_brokered_run", "callable"),
    ("blueprints.run", "start_interactive_pty_run", "callable"),
    ("blueprints.run", "_interactive_pty_input_limit", "callable"),
    ("services.commands.registry", "load_commands_registry", "callable"),
    ("services.commands.registry", "render_faq_markup", "callable"),
    ("services.commands.registry", "rewrite_command", "callable"),
    ("services.pty.service", "PtyTerminalCapture", "type"),
    ("services.pty.service", "_pty_input_max_bytes", "callable"),
    ("services.atlas.lookup", "list_entities", "callable"),
    ("services.atlas.lookup", "entity_detail", "callable"),
    ("services.atlas.lookup", "atlas_entities_export_csv", "callable"),
    ("services.workspace.files", "workspace_settings", "callable"),
    ("services.workspace.files", "ensure_session_workspace", "callable"),
    ("services.workspace.files", "list_workspace_files", "callable"),
)

_SINGLETON_BINDING_SOURCE_OF_TRUTH_PATHS = {
    "app/config.py",
    "app/core/database_access.py",
    "app/core/database.py",
    "app/core/process.py",
    "app/core/process_redis.py",
    "app/extensions.py",
}

_SINGLETON_BINDING_GUARD_BASELINE = frozenset(
    """
app/app.py: from config import CFG
app/blueprints/api_v1.py: from config import CFG
app/blueprints/api_v1_read.py: from config import CFG
app/blueprints/assets_audit.py: from config import CFG
app/blueprints/assets_diag.py: from config import CFG
app/blueprints/atlas.py: from config import CFG
app/blueprints/history.py: CFG assignment
app/blueprints/notifications.py: from config import CFG
app/blueprints/projects.py: from config import CFG
app/blueprints/projects_artifacts.py: from config import CFG
app/blueprints/projects_core.py: from config import CFG
app/blueprints/projects_packages.py: from config import CFG
app/blueprints/projects_report.py: from config import CFG
app/blueprints/run.py: from config import CFG
app/blueprints/schedules.py: from config import CFG
app/blueprints/secrets.py: from config import CFG
app/blueprints/teams.py: from config import CFG
app/blueprints/watchers.py: from config import CFG
""".strip().splitlines()
)

_BARE_DICT_CFG_SENTINEL_ALLOWLIST = frozenset({
    "tests/py/test_backend_modules.py: builtins_discovery.CFG bare-dict stale-global sentinel",
    "tests/py/test_backend_modules.py: builtins_misc.CFG bare-dict stale-global sentinel",
    "tests/py/test_backend_modules.py: builtins_runtime.CFG bare-dict stale-global sentinel",
    "tests/py/test_backend_modules.py: builtins_system.CFG bare-dict stale-global sentinel",
    "tests/py/test_backend_modules.py: builtins_workspace.CFG bare-dict stale-global sentinel",
})


def _wc_line_count(path: Path) -> int:
    content = path.read_bytes()
    line_count = content.count(b"\n")
    header = b"\n".join(content.splitlines()[:12])
    if b"SPDX-FileCopyrightText:" in header and b"SPDX-License-Identifier:" in header:
        # The standard two-line notice plus its separator is file metadata, not module code.
        line_count = max(0, line_count - 3)
    return line_count


_SQL_STRING_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bSELECT\b.+\bFROM\b",
        r"\bINSERT\s+INTO\b",
        r"\bUPDATE\b.+\bSET\b",
        r"\bDELETE\s+FROM\b",
        r"\bWHERE\b.+(?:=|\bIN\s*\(|\bLIKE\b|\bEXISTS\b|\bAND\b|\bOR\b)",
        r"\bJOIN\b.+\bON\b",
        r"\bORDER\s+BY\b",
        r"\bGROUP\s+BY\b",
        r"\b(?:session_id|team_id)\s*=\s*\?",
    )
)


def _looks_like_sql_string(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SQL_STRING_PATTERNS)


class _BlueprintPersistenceVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.connection_calls = 0
        self.connection_symbols = 0
        self.connection_aliases = set(_PERSISTENCE_CONNECTION_SYMBOLS)
        self.execute_calls = 0
        self.core_database_symbols = 0
        self.core_database_backend_symbols = 0
        self.cleanup_helper_symbols = 0
        self.sql_string_fragments = 0

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in self.connection_aliases:
            self.connection_calls += 1
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr == "db_connect":
                self.connection_calls += 1
            if node.func.attr in _PERSISTENCE_EXECUTE_METHODS:
                self.execute_calls += 1
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "core.database" or alias.name.startswith("core.database."):
                self.core_database_symbols += 1
            if alias.name == "core.database_backend" or alias.name.startswith("core.database_backend."):
                self.core_database_backend_symbols += 1
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name in _PERSISTENCE_CONNECTION_SYMBOLS:
                self.connection_symbols += 1
                self.connection_aliases.add(alias.asname or alias.name)
        if node.module == "core.database":
            self.core_database_symbols += len(node.names)
            self.cleanup_helper_symbols += sum(
                1 for alias in node.names if alias.name in _PERSISTENCE_CLEANUP_HELPERS
            )
        elif node.module == "core.database_backend":
            self.core_database_backend_symbols += len(node.names)
        elif node.module == "core":
            self.core_database_symbols += sum(1 for alias in node.names if alias.name == "database")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _looks_like_sql_string(node.value):
            self.sql_string_fragments += 1
        self.generic_visit(node)

    def metrics(self) -> BlueprintPersistenceMetrics:
        return BlueprintPersistenceMetrics(
            connection_calls=self.connection_calls,
            connection_symbols=self.connection_symbols,
            execute_calls=self.execute_calls,
            core_database_symbols=self.core_database_symbols,
            core_database_backend_symbols=self.core_database_backend_symbols,
            cleanup_helper_symbols=self.cleanup_helper_symbols,
            sql_string_fragments=self.sql_string_fragments,
        )


def _blueprint_persistence_metrics(path: Path) -> BlueprintPersistenceMetrics:
    visitor = _BlueprintPersistenceVisitor()
    visitor.visit(ast.parse(path.read_text(), filename=str(path)))
    return visitor.metrics()


def _blueprint_python_files(root: Path = _BLUEPRINT_DIR) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _blueprint_ratcheted_path(path: Path, root: Path = _BLUEPRINT_DIR) -> str:
    return path.relative_to(root).as_posix()


def _decomposed_route_contract_entries() -> list[tuple[str, str, str]]:
    from app import create_app

    app = create_app()
    entries = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint.split(".", 1)[0] not in _DECOMPOSED_ROUTE_BLUEPRINTS:
            continue
        for method in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            entries.append((method, rule.rule, rule.endpoint))
    return sorted(entries)


def _route_contract_digest(entries: list[tuple[str, str, str]]) -> str:
    canonical = "\n".join("\t".join(entry) for entry in entries)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _singleton_binding_guard_offenders(root: Path = _REPO_ROOT / "app") -> set[str]:
    offenders: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        try:
            relative_path = path.relative_to(_REPO_ROOT).as_posix()
        except ValueError:
            relative_path = path.relative_to(root).as_posix()
        if relative_path in _SINGLETON_BINDING_SOURCE_OF_TRUTH_PATHS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        core_database_aliases = {
            alias.asname
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "core.database" and alias.asname
        }
        core_database_aliases.update(
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "core"
            for alias in node.names
            if alias.name == "database"
        )
        core_process_aliases = {
            alias.asname
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name == "core.process" and alias.asname
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if module == "core.database" and alias.name in {"DB_BACKEND", "db_connect"}:
                        offenders.add(f"{relative_path}: from core.database import {alias.name}")
                    elif module == "core.process" and alias.name == "redis_client":
                        offenders.add(f"{relative_path}: from core.process import redis_client")
                    elif module == "config" and alias.name == "CFG":
                        offenders.add(f"{relative_path}: from config import CFG")
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "CFG":
                        offenders.add(f"{relative_path}: CFG assignment")
                    elif (
                        isinstance(target, ast.Name)
                        and target.id in {"DB_BACKEND", "db_connect"}
                        and isinstance(node.value, ast.Attribute)
                        and node.value.attr == target.id
                        and isinstance(node.value.value, ast.Name)
                        and node.value.value.id in core_database_aliases
                    ):
                        offenders.add(f"{relative_path}: {target.id} assignment from {node.value.value.id}")
                    elif (
                        isinstance(target, ast.Name)
                        and target.id == "redis_client"
                        and isinstance(node.value, ast.Attribute)
                        and node.value.attr == "redis_client"
                        and isinstance(node.value.value, ast.Name)
                        and node.value.value.id in core_process_aliases
                    ):
                        offenders.add(f"{relative_path}: redis_client assignment from {node.value.value.id}")
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "CFG":
                    offenders.add(f"{relative_path}: CFG assignment")
            elif isinstance(node, ast.Attribute) and node.attr == "CFG":
                if isinstance(node.value, ast.Name) and node.value.id in core_database_aliases:
                    offenders.add(f"{relative_path}: {node.value.id}.CFG")
                elif (
                    isinstance(node.value, ast.Attribute)
                    and node.value.attr == "database"
                    and isinstance(node.value.value, ast.Name)
                    and node.value.value.id == "core"
                ):
                    offenders.add(f"{relative_path}: core.database.CFG")
            elif isinstance(node, ast.ClassDef) and node.name in {"RedisClientProxy", "_RedisClientProxy"}:
                offenders.add(f"{relative_path}: local Redis proxy class {node.name}")
    return offenders


def _name_for_ast_expr(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name_for_ast_expr(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _bare_dict_cfg_monkeypatch_offenders(root: Path = _REPO_ROOT / "tests" / "py") -> set[str]:
    offenders: set[str] = set()
    for path in sorted(root.rglob("test_*.py")):
        relative_path = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "setattr"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "monkeypatch"
            ):
                continue
            if len(node.args) < 3:
                continue
            if not (isinstance(node.args[1], ast.Constant) and node.args[1].value == "CFG"):
                continue
            if not isinstance(node.args[2], ast.Dict):
                continue
            target_name = _name_for_ast_expr(node.args[0]) or "<unknown>"
            offenders.add(f"{relative_path}: {target_name}.CFG bare-dict stale-global sentinel")
    return offenders


def _required_module_size_ratchet_paths() -> set[str]:
    required = set()
    for pattern in _MODULE_SIZE_RATCHET_REQUIRED_PATTERNS:
        for path in _REPO_ROOT.glob(pattern):
            if path.is_file():
                required.add(path.relative_to(_REPO_ROOT).as_posix())
    return required


class TestBlueprintPersistenceBoundary:
    def test_blueprint_connection_detection_catches_reexported_aliases(self):
        source = """
from services.example import db_connect as connect

def route():
    with connect() as conn:
        return conn
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().connection_symbols == 1
        assert visitor.metrics().connection_calls == 1

    def test_blueprint_execute_family_detection_covers_bulk_and_scripts(self):
        source = """
def route(conn):
    conn.execute("SELECT 1")
    conn.executemany("INSERT INTO x VALUES (?)", [(1,), (2,)])
    conn.executescript("CREATE TABLE x (id INTEGER)")
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().execute_calls == 3

    def test_blueprint_execute_family_detection_is_conservative_by_design(self):
        source = """
def route(pipeline):
    pipeline.execute()
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().execute_calls == 1

    def test_blueprint_sql_string_detection_catches_owned_fragments(self):
        source = """
def run_owner_clause(prefix, team_id):
    if team_id:
        return f"{prefix}team_id = ?", [team_id]
    return f"{prefix}session_id = ? AND ({prefix}team_id IS NULL OR {prefix}team_id = '')"

def rows(conn):
    return conn.fetch_all("SELECT * FROM runs WHERE session_id = ?")
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().sql_string_fragments == 3

    def test_blueprint_sql_string_detection_ignores_route_text(self):
        source = """
def route(bp):
    bp.route("/history/bulk-delete", methods=["DELETE"])
    return "Delete selected runs from history."
"""
        visitor = _BlueprintPersistenceVisitor()
        visitor.visit(ast.parse(source))

        assert visitor.metrics().sql_string_fragments == 0

    def test_blueprint_scan_recurses_into_subpackages(self, tmp_path):
        blueprint_root = tmp_path / "blueprints"
        nested = blueprint_root / "history" / "queries.py"
        nested.parent.mkdir(parents=True)
        nested.write_text(
            """
def route(conn):
    conn.execute("SELECT 1")
""",
            encoding="utf-8",
        )

        actual = {
            _blueprint_ratcheted_path(path, blueprint_root): metrics
            for path in _blueprint_python_files(blueprint_root)
            if (metrics := _blueprint_persistence_metrics(path)).nonzero()
        }

        assert actual == {
            "history/queries.py": BlueprintPersistenceMetrics(execute_calls=1),
        }

    def test_blueprint_direct_database_access_matches_ratchet(self):
        actual = {
            _blueprint_ratcheted_path(path): metrics
            for path in _blueprint_python_files()
            if (metrics := _blueprint_persistence_metrics(path)).nonzero()
        }

        assert actual == _BLUEPRINT_PERSISTENCE_RATCHET, (
            "Blueprint persistence boundary drift detected. Move new database access "
            "behind services, or lower the ratchet after removing blueprint access.\n"
            f"actual={actual!r}"
        )

    def test_api_v1_service_package_stays_non_persistence(self):
        actual = {path.name for path in _API_V1_SERVICE_DIR.glob("*.py")}

        assert actual == _API_V1_SERVICE_ALLOWED_FILES, (
            "services/api_v1 should stay limited to auth, serialization, and OpenAPI helpers. "
            "Put persistence and database-backed operations in the owning domain service instead.\n"
            f"actual={sorted(actual)!r}"
        )


class TestBlueprintImportOrder:
    def test_split_route_modules_import_without_parent_order_cycle(self):
        script = (
            "import blueprints.run_broker, blueprints.run_client, blueprints.run_kill, "
            "blueprints.run_pty, blueprints.assets_diag, blueprints.assets_audit"
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=_REPO_ROOT,
            env={**os.environ, "PYTHONPATH": str(_REPO_ROOT / "app")},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


class TestScriptEntrypointLayout:
    def test_script_layout_and_compatibility_entrypoints_are_stable(self, tmp_path):
        scripts_root = _REPO_ROOT / "scripts"
        expected_directories = {
            "container",
            "development",
            "frontend",
            "generate",
            "hooks",
            "operations",
            "release",
            "test-support",
        }
        expected_top_level_files = {
            "backup_system.py",
            "build_release_payload.py",
            "capture_container_smoke_test_outputs.sh",
            "capture_ui_screenshots.sh",
            "check_container_licenses.py",
            "check_versions.sh",
            "container_smoke_test.sh",
            "generate_api_openapi.py",
            "generate_theme_examples.py",
            "migrate_sqlite_to_postgres.py",
            "record_demo.sh",
            "record_demo_mobile.sh",
            "restore_system.py",
            "run_playwright.sh",
            "run_postgres_tests.sh",
            "run_pytest.sh",
            "seed_history.py",
        }
        ignored_top_level_files = {".DS_Store"}
        actual_directories = {
            path.name
            for path in scripts_root.iterdir()
            if path.is_dir() and path.name != "__pycache__"
        }
        actual_top_level_files = {
            path.name
            for path in scripts_root.iterdir()
            if path.is_file() and path.name not in ignored_top_level_files
        }
        assert actual_directories == expected_directories
        assert actual_top_level_files == expected_top_level_files

        container_smoke_wrapper = (
            scripts_root / "container_smoke_test.sh"
        ).read_text(encoding="utf-8")
        assert 'sh "$ROOT_DIR/scripts/run_pytest.sh"' in container_smoke_wrapper
        assert "python3 -m pytest" not in container_smoke_wrapper

        wrappers = {
            "backup_system.py": "operations/backup_system.py",
            "build_release_payload.py": "release/build_release_payload.py",
            "capture_container_smoke_test_outputs.sh": (
                "test-support/capture_container_smoke_test_outputs.sh"
            ),
            "capture_ui_screenshots.sh": "development/capture_ui_screenshots.sh",
            "check_container_licenses.py": "release/check_container_licenses.py",
            "check_versions.sh": "release/check_versions.sh",
            "generate_api_openapi.py": "generate/generate_api_openapi.py",
            "generate_theme_examples.py": "generate/generate_theme_examples.py",
            "migrate_sqlite_to_postgres.py": (
                "operations/migrate_sqlite_to_postgres.py"
            ),
            "record_demo.sh": "development/record_demo.sh",
            "record_demo_mobile.sh": "development/record_demo_mobile.sh",
            "restore_system.py": "operations/restore_system.py",
            "seed_history.py": "development/seed_history.py",
        }
        for wrapper_name, implementation_path in wrappers.items():
            wrapper = scripts_root / wrapper_name
            text = wrapper.read_text(encoding="utf-8")
            assert implementation_path in text
            assert stat.S_IMODE(wrapper.stat().st_mode) & stat.S_IXUSR
            assert '"$@"' in text or "*sys.argv[1:]" in text
            assert "exec " in text or "os.execv(" in text

        help_wrappers = (
            "backup_system.py",
            "build_release_payload.py",
            "capture_ui_screenshots.sh",
            "check_versions.sh",
            "migrate_sqlite_to_postgres.py",
            "restore_system.py",
            "seed_history.py",
        )
        for wrapper_name in help_wrappers:
            wrapper = scripts_root / wrapper_name
            command = (
                [sys.executable, str(wrapper), "--help"]
                if wrapper.suffix == ".py" or wrapper_name == "check_versions.sh"
                else [str(wrapper), "--help"]
            )
            result = subprocess.run(
                command,
                cwd=tmp_path,
                text=True,
                capture_output=True,
                check=False,
            )
            assert result.returncode == 0, (
                f"{wrapper_name} failed outside the repository root:\n{result.stderr}"
            )


class TestDecomposedRouteContract:
    def test_decomposed_blueprint_route_contract_matches_pre_split_set(self):
        entries = _decomposed_route_contract_entries()
        actual_count = len(entries)
        actual_digest = _route_contract_digest(entries)

        assert actual_count == _DECOMPOSED_ROUTE_CONTRACT_COUNT, (
            "Decomposed blueprint route count changed. Review the route contract "
            "before updating the expected count.\n"
            + "\n".join(repr(entry) for entry in entries)
        )
        assert actual_digest == _DECOMPOSED_ROUTE_CONTRACT_SHA256, (
            "Decomposed blueprint route contract drifted. Keep method, path, and "
            "endpoint names stable unless this is an intentional route change.\n"
            + "\n".join(repr(entry) for entry in entries)
        )


class TestModuleSizeRatchet:
    def test_tracked_modules_do_not_grow_past_baseline(self):
        over_budget = []
        for budget in _MODULE_SIZE_RATCHET:
            path = _REPO_ROOT / budget.path
            assert path.exists(), f"Tracked module size budget path is missing: {budget.path}"
            actual = _wc_line_count(path)
            if actual > budget.max_lines:
                over_budget.append(
                    f"{budget.path}: {actual} lines > {budget.max_lines} "
                    f"({budget.treatment})"
                )

        assert not over_budget, (
            "Module size ratchet drift detected. Keep the tracked file at or below "
            "its current baseline, split it, or intentionally lower/replace the "
            "budget after decomposition.\n"
            + "\n".join(over_budget)
        )

    def test_decomposed_module_families_are_all_classified(self):
        tracked = {budget.path for budget in _MODULE_SIZE_RATCHET}
        missing = sorted(_required_module_size_ratchet_paths() - tracked)

        assert not missing, (
            "Module size ratchet coverage drift detected. Add a budget treatment "
            "for each new file in the decomposed families.\n"
            + "\n".join(missing)
        )


class TestSingletonDependencyGuard:
    def test_singleton_binding_guard_flags_synthetic_offenders(self, tmp_path):
        app_root = tmp_path / "app"
        service_module = app_root / "services" / "example.py"
        service_module.parent.mkdir(parents=True)
        service_module.write_text(
            """
from config import CFG
from core import database
from core.database import DB_BACKEND, db_connect
import core.database as database_owner
import core.process as process_owner
from core.process import redis_client


DB_BACKEND = database.DB_BACKEND
db_connect = database_owner.db_connect
redis_client = process_owner.redis_client


def uses_database_owner_module():
    return database.db_connect, database.CFG, database_owner.CFG


class RedisClientProxy:
    pass
""",
            encoding="utf-8",
        )
        config_rebind_module = app_root / "services" / "config_rebind.py"
        config_rebind_module.write_text("CFG = object()\n", encoding="utf-8")

        offenders = _singleton_binding_guard_offenders(app_root)

        assert offenders == {
            "services/config_rebind.py: CFG assignment",
            "services/example.py: from config import CFG",
            "services/example.py: from core.database import DB_BACKEND",
            "services/example.py: from core.database import db_connect",
            "services/example.py: from core.process import redis_client",
            "services/example.py: DB_BACKEND assignment from database",
            "services/example.py: database.CFG",
            "services/example.py: database_owner.CFG",
            "services/example.py: db_connect assignment from database_owner",
            "services/example.py: local Redis proxy class RedisClientProxy",
            "services/example.py: redis_client assignment from process_owner",
        }

    def test_no_new_local_singleton_bindings_beyond_phase0_baseline(self):
        offenders = _singleton_binding_guard_offenders()
        new_offenders = sorted(offenders - _SINGLETON_BINDING_GUARD_BASELINE)
        bare_dict_cfg_offenders = sorted(
            _bare_dict_cfg_monkeypatch_offenders() - _BARE_DICT_CFG_SENTINEL_ALLOWLIST
        )

        assert not new_offenders, (
            "New local singleton bindings detected. Use the shared accessor/helper/proxy "
            "conventions or update the Phase 0 dependency-injection plan before expanding "
            "the approved compatibility baseline:\n"
            + "\n".join(f"  {offender}" for offender in new_offenders)
        )
        assert not bare_dict_cfg_offenders, (
            "Bare-dict CFG monkeypatches detected. Use build_test_config(...) for CFG "
            "replacement tests, or document an intentional stale-global sentinel in "
            "_BARE_DICT_CFG_SENTINEL_ALLOWLIST:\n"
            + "\n".join(f"  {offender}" for offender in bare_dict_cfg_offenders)
        )


class TestPublicImportCompatibility:
    def test_moved_public_symbols_remain_available_from_parent_modules(self):
        issues = []
        for module_name, symbol, expected_kind in _PUBLIC_IMPORT_COMPATIBILITY_CONTRACT:
            module = importlib.import_module(module_name)
            if not hasattr(module, symbol):
                issues.append(f"{module_name}.{symbol}: missing")
                continue
            value = getattr(module, symbol)
            if expected_kind == "callable" and not callable(value):
                issues.append(f"{module_name}.{symbol}: expected callable, got {type(value).__name__}")
            elif expected_kind == "type" and not isinstance(value, type):
                issues.append(f"{module_name}.{symbol}: expected type, got {type(value).__name__}")

        assert not issues, (
            "Public import compatibility drift detected for moved decomposition symbols.\n"
            + "\n".join(issues)
        )


class TestTeamModeScopePredicates:
    def test_direct_team_run_predicates_use_owner_scope_helpers(self):
        issues = []
        for path in sorted((_REPO_ROOT / "app").rglob("*.py")):
            relative = path.relative_to(_REPO_ROOT)
            for line_number, source in _team_scope_sql_fragments(path):
                qualified_match = _DIRECT_TEAM_RUN_PREDICATE_RE.search(source)
                unqualified_match = (
                    _RUN_SQL_RE.search(source)
                    and _UNQUALIFIED_TEAM_RUN_PREDICATE_RE.search(source)
                )
                if not (qualified_match or unqualified_match):
                    continue
                snippet = " ".join(source.split())[:180]
                issues.append(f"  {relative}:{line_number}: {snippet}")

        assert not issues, (
            "Direct team run predicates can hide team-owned runs from other members. "
            "Use owner_scope.predicate(), _run_owner_clause(), or another shared "
            "owner-scope helper instead of combining session_id = ? with team_id = ? on runs:\n"
            + "\n".join(issues)
        )
