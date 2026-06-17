// Project target editor copy and value validation.

const ProjectTargetValidation = (() => {
  const TARGET_TYPES = [
    { value: 'domain', label: 'domain' },
    { value: 'url', label: 'url' },
    { value: 'host', label: 'host' },
    { value: 'ip', label: 'ip' },
  ];
  const TARGET_NOTES_MAX_LENGTH = 20000;
  const DOMAIN_RE = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/i;
  const HOST_RE = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*\.?$/i;
  const IPV4_RE = /^(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)$/;
  const TARGET_VALUE_HELP = {
    domain: {
      placeholder: 'target.example.com',
      help: 'Domain name only. Examples: darklab.sh, api.darklab.sh',
      error: 'Use a domain name, such as darklab.sh or api.darklab.sh.',
    },
    url: {
      placeholder: 'https://target.example.com/path',
      help: 'Full URL including scheme. Examples: https://darklab.sh, https://api.darklab.sh/login',
      error: 'Use a full HTTP or HTTPS URL, such as https://darklab.sh/login.',
    },
    host: {
      placeholder: 'host.example.com',
      help: 'Hostname or IP address. Examples: api.darklab.sh, 192.0.2.10',
      error: 'Use a hostname or IP address, such as api.darklab.sh or 192.0.2.10.',
    },
    ip: {
      placeholder: '192.0.2.10',
      help: 'Single IPv4 or IPv6 address. Examples: 192.0.2.10, 2001:db8::10',
      error: 'Use a single IPv4 or IPv6 address, such as 192.0.2.10 or 2001:db8::10.',
    },
  };

  function _isValidIpv6Address(value) {
    const candidate = String(value || '').trim();
    if (!candidate || !candidate.includes(':') || /[\s/]/.test(candidate)) return false;
    try {
      return !!new URL(`http://[${candidate}]`).hostname;
    } catch (_) {
      return false;
    }
  }

  function isValidIpAddress(value) {
    const candidate = String(value || '').trim();
    return IPV4_RE.test(candidate) || _isValidIpv6Address(candidate);
  }

  function isValidDomain(value) {
    return DOMAIN_RE.test(String(value || '').trim());
  }

  function isValidHost(value) {
    const candidate = String(value || '').trim();
    if (!candidate || /[:/?#@\s]/.test(candidate)) return isValidIpAddress(candidate);
    return HOST_RE.test(candidate);
  }

  function isValidUrl(value) {
    const candidate = String(value || '').trim();
    if (!candidate || /\s/.test(candidate)) return false;
    try {
      const parsed = new URL(candidate);
      return ['http:', 'https:'].includes(parsed.protocol) && !!parsed.hostname;
    } catch (_) {
      return false;
    }
  }

  function helpForType(type) {
    const normalized = String(type || 'domain').trim();
    return TARGET_VALUE_HELP[normalized] || TARGET_VALUE_HELP.domain;
  }

  function valueValidationError(type, value) {
    const normalized = String(type || 'domain').trim();
    const candidate = String(value || '').trim();
    if (!candidate) return 'Enter a target value before saving.';
    const validators = {
      domain: isValidDomain,
      url: isValidUrl,
      host: isValidHost,
      ip: isValidIpAddress,
    };
    const validator = validators[normalized] || validators.domain;
    if (validator(candidate)) return '';
    const copy = helpForType(normalized);
    return `The target value does not match the selected type. ${copy.error}`;
  }

  function notesValidationError(notes) {
    const length = String(notes || '').trim().length;
    if (length <= TARGET_NOTES_MAX_LENGTH) return '';
    return `Target notes must be ${TARGET_NOTES_MAX_LENGTH.toLocaleString()} characters or fewer.`;
  }

  return {
    TARGET_TYPES,
    TARGET_NOTES_MAX_LENGTH,
    TARGET_VALUE_HELP,
    helpForType,
    valueValidationError,
    notesValidationError,
  };
})();


const {
  TARGET_NOTES_MAX_LENGTH,
  TARGET_TYPES,
  TARGET_VALUE_HELP,
  helpForType,
  notesValidationError,
  valueValidationError,
} = ProjectTargetValidation;

export {
  ProjectTargetValidation,
  TARGET_NOTES_MAX_LENGTH,
  TARGET_TYPES,
  TARGET_VALUE_HELP,
  helpForType,
  notesValidationError,
  valueValidationError,
};
