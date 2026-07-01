"""Backfill URL host entity links when the host already exists."""

from .runner import Migration

MIGRATION = Migration(
    version="0038",
    name="url_host_entity_links",
    statements=(
        """
        WITH url_authorities AS (
            SELECT
                id AS url_id,
                session_id,
                COALESCE(team_id, '') AS team_id,
                REGEXP_REPLACE(
                    SPLIT_PART(
                        REGEXP_REPLACE(canonical_value, '^[a-z][a-z0-9+.-]*://', ''),
                        '/',
                        1
                    ),
                    '^.*@',
                    ''
                ) AS authority
            FROM entities
            WHERE type = 'url' AND COALESCE(host_entity_id, '') = ''
        ),
        url_hosts AS (
            SELECT
                url_id,
                session_id,
                team_id,
                CASE
                    WHEN LOWER(TRIM(BOTH '[]' FROM host_value)) ~
                        '^[0-9]{1,3}(\\.[0-9]{1,3}){3}$'
                      OR LOWER(TRIM(BOTH '[]' FROM host_value)) LIKE '%:%'
                    THEN 'ip'
                    ELSE 'domain'
                END AS host_type,
                LOWER(TRIM(BOTH '[]' FROM host_value)) AS host_value
            FROM (
                SELECT
                    url_id,
                    session_id,
                    team_id,
                    CASE
                        WHEN authority LIKE '[%' THEN SUBSTRING(authority FROM '^\\[([^]]+)\\]')
                        ELSE SPLIT_PART(authority, ':', 1)
                    END AS host_value
                FROM url_authorities
            ) extracted_hosts
            WHERE host_value IS NOT NULL AND host_value != ''
        )
        UPDATE entities AS url_e
        SET host_entity_id = host_e.id
        FROM url_hosts
        JOIN entities AS host_e
          ON host_e.type = url_hosts.host_type
         AND host_e.canonical_value = url_hosts.host_value
         AND host_e.session_id = url_hosts.session_id
         AND COALESCE(host_e.team_id, '') = url_hosts.team_id
        WHERE url_e.id = url_hosts.url_id
          AND url_e.type = 'url'
          AND COALESCE(url_e.host_entity_id, '') = ''
        """,
    ),
)
