// ── Shared utility module ──

function escapeHtml(t) {
  return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeRedactionRules(rules) {
  if (!Array.isArray(rules)) return [];
  return rules
    .filter(rule => rule && typeof rule === 'object')
    .map(rule => {
      const pattern = typeof rule.pattern === 'string' ? rule.pattern : '';
      if (!pattern.trim()) return null;
      const replacement = typeof rule.replacement === 'string' ? rule.replacement : '[redacted]';
      const flags = typeof rule.flags === 'string'
        ? Array.from(new Set(rule.flags.toLowerCase().split('').filter(ch => ch === 'i' || ch === 'm'))).join('')
        : '';
      try {
        return {
          label: typeof rule.label === 'string' ? rule.label.trim() : '',
          pattern,
          replacement,
          flags,
          regex: new RegExp(pattern, `g${flags}`),
        };
      } catch (_) {
        return null;
      }
    })
    .filter(Boolean);
}

function applyRedactionRules(text, rules) {
  let value = String(text ?? '');
  for (const rule of normalizeRedactionRules(rules)) {
    value = value.replace(rule.regex, rule.replacement);
  }
  return value;
}

function redactLineEntries(entries, rules) {
  return (Array.isArray(entries) ? entries : [])
    .map(item => {
      if (typeof item === 'string') return applyRedactionRules(item, rules);
      if (!item || typeof item !== 'object' || typeof item.text !== 'string') return null;
      return {
        ...item,
        text: applyRedactionRules(item.text, rules),
      };
    })
    .filter(Boolean);
}

// Render a small Markdown subset for MOTD: **bold**, `code`, [text](url), newlines.
// escapeHtml is applied first to prevent XSS, then patterns are applied so the
// operator notice stays useful without needing a full Markdown parser.
function renderMotd(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\n/g, '<br>');
}

function _copyTextFallback(text) {
  return new Promise((resolve, reject) => {
    if (typeof document === 'undefined' || !document.body) {
      reject(new Error('Clipboard is not available'));
      return;
    }
    const textarea = document.createElement('textarea');
    textarea.value = String(text);
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '-9999px';
    textarea.style.left = '-9999px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
      copied = typeof document.execCommand === 'function' && document.execCommand('copy');
    } catch (_) {
      copied = false;
    }
    textarea.remove();
    if (copied) resolve(true);
    else reject(new Error('Copy command failed'));
  });
}

async function copyTextToClipboard(text) {
  const value = String(text ?? '');
  if (!value) throw new Error('Cannot copy empty text');
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch (_) {
      // Fall through to the legacy copy command fallback below.
    }
  }
  return _copyTextFallback(value);
}

async function shareUrl(url) {
  // navigator.share requires a user gesture and a secure context (HTTPS).
  // Because shareUrl is always called from inside a fetch .then() callback
  // (creating the snapshot), the transient activation has already expired by
  // the time we get here — a direct navigator.share() call will always fail
  // with NotAllowedError. Instead we always copy to clipboard first (reliable),
  // then surface a share button in the toast so the user can open the native
  // share sheet with a fresh gesture from that tap.
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  try {
    await copyTextToClipboard(url);
  } catch (_) {
    // Clipboard unavailable — surface the URL in a native prompt as last resort.
    if (typeof window !== 'undefined' && typeof window.prompt === 'function') {
      window.prompt('Copy the link:', url);
    }
    return;
  }
  if (canShare) {
    showToast('Link copied to clipboard', 'success', {
      label: 'share ↗',
      onClick: () => { navigator.share({ url }).catch(() => {}); },
    });
  } else {
    showToast('Link copied to clipboard');
  }
}

function showToast(msg, tone = 'success', action = null) {
  // Toasts are transient UI feedback only; avoid stacking timers by resetting
  // the hide timer whenever a new message reuses the same element.
  const toast = document.getElementById('permalink-toast');
  const isError = tone === 'error' || /^(failed|unable|error|\[.*error\])/i.test(String(msg || ''));
  toast.classList.remove('toast-has-action');
  toast.textContent = msg;
  if (action && action.label && typeof action.onClick === 'function') {
    const btn = document.createElement('button');
    btn.className = 'toast-action-btn';
    btn.textContent = action.label;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      toast.classList.remove('show');
      toast.classList.remove('toast-has-action');
      action.onClick();
    }, { once: true });
    toast.classList.add('toast-has-action');
    toast.appendChild(btn);
  }
  toast.classList.toggle('toast-error', isError);
  toast.classList.toggle('toast-success', !isError);
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
    toast.classList.remove('toast-has-action');
  }, action ? 5000 : 2500);
}
