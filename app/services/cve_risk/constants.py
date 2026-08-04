# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable source and attribution contracts for public CVE risk data."""

EPSS_SOURCE = "epss"
KEV_SOURCE = "kev"
KNOWN_SOURCES = (EPSS_SOURCE, KEV_SOURCE)

EPSS_SOURCE_URL = "https://epss.cyentia.com/epss_scores-current.csv.gz"
EPSS_TERMS_URL = "https://www.first.org/about/policies/terms"
EPSS_ATTRIBUTION = (
    "Exploit Prediction Scoring System (EPSS) data provided by FIRST. "
    "EPSS estimates exploitation probability and is not a complete risk score."
)

KEV_SOURCE_URL = (
    "https://www.cisa.gov/sites/default/files/feeds/"
    "known_exploited_vulnerabilities.json"
)
KEV_TERMS_URL = "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"
KEV_ATTRIBUTION = (
    "Known Exploited Vulnerabilities catalog data provided by CISA. "
    "Catalog inclusion and BOD 22-01 dates do not create a private-sector remediation SLA."
)

SOURCE_ATTRIBUTION = {
    EPSS_SOURCE: EPSS_ATTRIBUTION,
    KEV_SOURCE: KEV_ATTRIBUTION,
}
SOURCE_TERMS_URL = {
    EPSS_SOURCE: EPSS_TERMS_URL,
    KEV_SOURCE: KEV_TERMS_URL,
}
SOURCE_URL = {
    EPSS_SOURCE: EPSS_SOURCE_URL,
    KEV_SOURCE: KEV_SOURCE_URL,
}
