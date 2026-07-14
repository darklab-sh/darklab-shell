# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Snapshot severity and stable comparison identity on finding occurrences."""

from .runner import Migration


MIGRATION = Migration(
    version="0044",
    name="finding_occurrence_comparison",
    statements=(),
    sqlite_statements=(
        "ALTER TABLE findings_occurrences ADD COLUMN observed_severity TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings_occurrences ADD COLUMN comparison_key TEXT NOT NULL DEFAULT ''",
        """
        UPDATE findings_occurrences
        SET observed_severity = COALESCE(
            (SELECT f.severity FROM findings f WHERE f.id = findings_occurrences.finding_id),
            ''
        ),
        comparison_key = COALESCE((
            SELECT 'raw:' || COALESCE(f.tool_root, '') || char(31)
                || COALESCE(f.kind, 'finding') || char(31)
                || COALESCE(f.subject_key, '') || char(31)
                || COALESCE(NULLIF(findings_occurrences.snippet, ''), f.raw_line, f.title, '')
            FROM findings f WHERE f.id = findings_occurrences.finding_id
        ), '')
        WHERE observed_severity = '' OR comparison_key = ''
        """,
        "DROP TRIGGER IF EXISTS findings_legacy_ai",
        """
        CREATE TRIGGER findings_legacy_ai AFTER INSERT ON findings
        WHEN NEW.run_id != ''
        BEGIN
            INSERT INTO findings_occurrences (
                finding_id, run_id, line_number, snippet, seen_at, observed_severity, comparison_key
            ) VALUES (
                NEW.id,
                NEW.run_id,
                COALESCE(NEW.line_number, 0),
                COALESCE(NEW.raw_line, ''),
                COALESCE(NULLIF(NEW.created, ''), datetime('now')),
                COALESCE(NEW.severity, ''),
                'raw:' || COALESCE(NEW.tool_root, '') || char(31)
                    || COALESCE(NEW.kind, 'finding') || char(31)
                    || COALESCE(NEW.subject_key, '') || char(31)
                    || COALESCE(NEW.raw_line, NEW.title, '')
            )
            ON CONFLICT(finding_id, run_id, line_number) DO UPDATE SET
                observed_severity = excluded.observed_severity,
                comparison_key = excluded.comparison_key;
            UPDATE findings
               SET first_run_id = CASE WHEN first_run_id = '' THEN NEW.run_id ELSE first_run_id END,
                   last_run_id = NEW.run_id,
                   first_seen_at = CASE
                       WHEN first_seen_at = '' THEN COALESCE(NULLIF(NEW.created, ''), datetime('now'))
                       ELSE first_seen_at
                   END,
                   last_seen_at = COALESCE(NULLIF(NEW.created, ''), datetime('now')),
                   occurrence_count = (
                       SELECT COUNT(*) FROM findings_occurrences WHERE finding_id = NEW.id
                   ),
                   status = CASE WHEN NEW.review_state != '' THEN NEW.review_state ELSE status END,
                   kind = CASE WHEN NEW.scope != '' THEN NEW.scope ELSE kind END,
                   signature_hash = CASE
                       WHEN signature_hash = '' THEN COALESCE(NULLIF(NEW.fingerprint, ''), NEW.id)
                       ELSE signature_hash
                   END
             WHERE id = NEW.id;
        END
        """,
    ),
    postgres_statements=(
        "ALTER TABLE findings_occurrences ADD COLUMN IF NOT EXISTS observed_severity TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE findings_occurrences ADD COLUMN IF NOT EXISTS comparison_key TEXT NOT NULL DEFAULT ''",
        """
        UPDATE findings_occurrences fo
        SET observed_severity = COALESCE(f.severity, ''),
            comparison_key = 'raw:' || COALESCE(f.tool_root, '') || chr(31)
                || COALESCE(f.kind, 'finding') || chr(31)
                || COALESCE(f.subject_key, '') || chr(31)
                || COALESCE(NULLIF(fo.snippet, ''), f.raw_line, f.title, '')
        FROM findings f
        WHERE f.id = fo.finding_id AND (fo.observed_severity = '' OR fo.comparison_key = '')
        """,
        """
        CREATE OR REPLACE FUNCTION findings_legacy_ai_fn()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.run_id != '' THEN
                INSERT INTO findings_occurrences (
                    finding_id, run_id, line_number, snippet, seen_at,
                    observed_severity, comparison_key
                ) VALUES (
                    NEW.id,
                    NEW.run_id,
                    COALESCE(NEW.line_number, 0),
                    COALESCE(NEW.raw_line, ''),
                    COALESCE(NULLIF(NEW.created, ''), CURRENT_TIMESTAMP::text),
                    COALESCE(NEW.severity, ''),
                    'raw:' || COALESCE(NEW.tool_root, '') || chr(31)
                        || COALESCE(NEW.kind, 'finding') || chr(31)
                        || COALESCE(NEW.subject_key, '') || chr(31)
                        || COALESCE(NEW.raw_line, NEW.title, '')
                )
                ON CONFLICT (finding_id, run_id, line_number) DO UPDATE SET
                    observed_severity = EXCLUDED.observed_severity,
                    comparison_key = EXCLUDED.comparison_key;
                UPDATE findings
                   SET first_run_id = CASE WHEN first_run_id = '' THEN NEW.run_id ELSE first_run_id END,
                       last_run_id = NEW.run_id,
                       first_seen_at = CASE
                           WHEN first_seen_at = '' THEN COALESCE(NULLIF(NEW.created, ''), CURRENT_TIMESTAMP::text)
                           ELSE first_seen_at
                       END,
                       last_seen_at = COALESCE(NULLIF(NEW.created, ''), CURRENT_TIMESTAMP::text),
                       occurrence_count = (
                           SELECT COUNT(*) FROM findings_occurrences WHERE finding_id = NEW.id
                       ),
                       status = CASE WHEN NEW.review_state != '' THEN NEW.review_state ELSE status END,
                       kind = CASE WHEN NEW.scope != '' THEN NEW.scope ELSE kind END,
                       signature_hash = CASE
                           WHEN signature_hash = '' THEN COALESCE(NULLIF(NEW.fingerprint, ''), NEW.id)
                           ELSE signature_hash
                       END
                 WHERE id = NEW.id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """,
        "DROP TRIGGER IF EXISTS findings_legacy_ai ON findings",
        """
        CREATE TRIGGER findings_legacy_ai
        AFTER INSERT ON findings
        FOR EACH ROW EXECUTE FUNCTION findings_legacy_ai_fn()
        """,
    ),
)
