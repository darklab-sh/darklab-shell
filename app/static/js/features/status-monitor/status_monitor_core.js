// darklab_shell Status Monitor pure helpers.
// Rendering, polling, and action wiring stay in status_monitor.js.

  const GRACEFUL_TERMINATION_EXIT_CODES = new Set([-15]);

  function normalizedExitCode(exitCode) {
    if (exitCode === null || exitCode === undefined || exitCode === '') return null;
    const number = Number(exitCode);
    return Number.isFinite(number) ? number : null;
  }

  function isGracefulTerminationExitCode(exitCode) {
    const code = normalizedExitCode(exitCode);
    return code !== null && GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }

  function isFailedExitCode(exitCode) {
    const code = normalizedExitCode(exitCode);
    return code !== null && code !== 0 && !GRACEFUL_TERMINATION_EXIT_CODES.has(code);
  }

  function exitCodeLabel(exitCode) {
    const code = normalizedExitCode(exitCode);
    if (code === null) return 'active';
    if (isGracefulTerminationExitCode(code)) return 'terminated';
    return `exit ${code}`;
  }

  function formatElapsed(started) {
    const start = Date.parse(String(started || ''));
    if (!Number.isFinite(start)) return '-';
    const total = Math.max(0, Math.floor((Date.now() - start) / 1000));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    return [hours, minutes, seconds].map(value => String(value).padStart(2, '0')).join(':');
  }

  function shortRunId(run) {
    return String(run?.run_id || run?.id || '').slice(0, 8) || '-';
  }

  function formatCpuPercent(value) {
    if (value === null || value === undefined) return 'n/a';
    if (!Number.isFinite(Number(value))) return 'collecting';
    const cpu = Math.min(100, Math.max(0, Number(value)));
    return `${cpu.toFixed(cpu >= 10 ? 0 : 1)}%`;
  }

  function isTelemetryNumber(value) {
    return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
  }

  function formatMemoryBytes(value) {
    if (value === null || value === undefined) return 'n/a';
    const bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes < 0) return '-';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    const precision = unitIndex === 0 || size >= 10 ? 0 : 1;
    return `${size.toFixed(precision)} ${units[unitIndex]}`;
  }

  function formatDurationSeconds(value) {
    if (!isTelemetryNumber(value)) return 'n/a';
    const total = Math.max(0, Number(value));
    if (total >= 3600) {
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor((total % 3600) / 60);
      return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
    }
    if (total >= 60) {
      const minutes = Math.floor(total / 60);
      const seconds = Math.round(total % 60);
      return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
    }
    return `${total.toFixed(total >= 10 ? 0 : 1)}s`;
  }

  function formatCount(value) {
    const count = Number(value);
    if (!Number.isFinite(count)) return '0';
    return new Intl.NumberFormat().format(count);
  }

  function truncateText(value, maxLength = 64) {
    const text = String(value || '').trim();
    if (text.length <= maxLength) return text;
    return `${text.slice(0, Math.max(0, maxLength - 1))}…`;
  }

  function hashString(value) {
    let hash = 0;
    const text = String(value || '');
    for (let index = 0; index < text.length; index += 1) {
      hash = ((hash << 5) - hash) + text.charCodeAt(index);
      hash |= 0;
    }
    return Math.abs(hash);
  }

  function normalizedHash(value) {
    return hashString(String(value || '').trim().toLowerCase());
  }

  function seededUnit(seed) {
    const value = Math.sin(Number(seed) || 1) * 10000;
    return value - Math.floor(value);
  }

  function parseIsoDateOnly(value) {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || '').trim());
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const timestamp = Date.UTC(year, month - 1, day);
    return Number.isFinite(timestamp) ? timestamp : null;
  }

  function formatIsoDateOnly(timestamp) {
    return new Date(timestamp).toISOString().slice(0, 10);
  }

  function isoWeekdayRow(timestamp) {
    const day = new Date(timestamp).getUTCDay();
    return day === 0 ? 7 : day;
  }

  window.DarklabStatusMonitorCore = {
    normalizedExitCode,
    isGracefulTerminationExitCode,
    isFailedExitCode,
    exitCodeLabel,
    formatElapsed,
    shortRunId,
    formatCpuPercent,
    isTelemetryNumber,
    formatMemoryBytes,
    formatDurationSeconds,
    formatCount,
    truncateText,
    hashString,
    normalizedHash,
    seededUnit,
    parseIsoDateOnly,
    formatIsoDateOnly,
    isoWeekdayRow,
  };
