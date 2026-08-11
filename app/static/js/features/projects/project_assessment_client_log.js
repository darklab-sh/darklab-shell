// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Bounded Assessment browser-failure event and correlation reporting.

const safeDetailKeys = [
  'action',
  'assessment_id',
  'check_id',
  'correlation_id',
  'job_id',
  'phase',
  'profile_key',
  'project_id',
];

function errorStatus(error) {
  const value = Number(error?.status || error?.statusCode || 0);
  return Number.isInteger(value) && value >= 100 && value <= 599 ? value : 0;
}

function networkDegraded(error) {
  const name = String(error?.name || '').trim();
  const message = String(error?.message || error || '').trim().toLowerCase();
  return name === 'AbortError'
    || name === 'NetworkError'
    || /failed to fetch|fetch failed|networkerror|network request failed/.test(message);
}

function assessmentClientLogLevel(error) {
  const status = errorStatus(error);
  if (status >= 500) return 'error';
  if (status >= 400) return 'warning';
  return networkDegraded(error) ? 'warning' : 'error';
}

function logAssessmentClientFailure(context, event, error, details = {}) {
  const stableEvent = String(event || 'PROJECT_ASSESSMENT_CLIENT_FAILED').trim().toUpperCase();
  const payload = {
    page: 'project_assessment',
    event: stableEvent,
    level: assessmentClientLogLevel(error),
  };
  safeDetailKeys.forEach((key) => {
    const value = String(details?.[key] || '').trim();
    if (value) payload[key] = value;
  });
  const status = errorStatus(error);
  if (status) payload.status = status;
  context?.logClientError?.(stableEvent, error, payload);
}

export { assessmentClientLogLevel, logAssessmentClientFailure };
