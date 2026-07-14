"""Request resolution shared by run comparison routes."""

from flask import jsonify

from services.projects.comparisons import compare_project_runs
from services.projects.contracts import ProjectWorkspaceError


def resolve_compare_request(owner_scope, left_id, right_id, project_id="", baseline_label=""):
    project_comparison = None
    if project_id:
        try:
            project_comparison = compare_project_runs(owner_scope, project_id, {
                "left_run_id": left_id,
                "right_run_id": right_id,
                "baseline_label": baseline_label,
            })
        except ProjectWorkspaceError as exc:
            return "", "", None, (jsonify({"error": str(exc)}), 400)
        if project_comparison is None:
            return "", "", None, (jsonify({"error": "project not found"}), 404)
        left_id = str(project_comparison.get("left_run_id") or "")
        right_id = str(project_comparison.get("right_run_id") or "")
    if not left_id or not right_id:
        return "", "", None, (jsonify({"error": "left and right run ids are required"}), 400)
    if left_id == right_id:
        return "", "", None, (jsonify({"error": "Choose two different runs to compare"}), 400)
    return left_id, right_id, project_comparison, None
