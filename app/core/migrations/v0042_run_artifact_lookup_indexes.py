"""Add run-leading indexes for run artifact lookups."""

from .runner import Migration


MIGRATION = Migration(
    version="0042",
    name="run_artifact_lookup_indexes",
    statements=(
        """
        CREATE INDEX IF NOT EXISTS idx_run_file_artifacts_run_created_path
        ON run_file_artifacts (run_id, created ASC, workspace_path ASC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_run_file_artifacts_run_created_id
        ON run_file_artifacts (run_id, created DESC, id DESC)
        """,
    ),
)
