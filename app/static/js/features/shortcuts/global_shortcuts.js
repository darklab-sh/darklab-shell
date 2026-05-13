function eventMatchesCode(e, code) {
  return !!(e && e.code === code);
}

const MAC_OPTION_KEY_ALIASES = {
  f: ['ƒ'],
};

function eventMatchesLetter(e, letter) {
  if (eventMatchesCode(e, `Key${letter.toUpperCase()}`)) return true;
  const key = e && typeof e.key === 'string' ? e.key.toLowerCase() : '';
  const normalizedLetter = String(letter || '').toLowerCase();
  return key === normalizedLetter || (MAC_OPTION_KEY_ALIASES[normalizedLetter] || []).includes(key);
}

function eventMatchesDigit(e, digit) {
  if (eventMatchesCode(e, `Digit${digit}`)) return true;
  return !!(e && e.key === String(digit));
}

function handleTabShortcut(e) {
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  // Letter chords (T, W) require no Shift — Alt+Shift+T is the theme-selector
  // chrome shortcut and must fall through to handleChromeShortcut.
  if (!e.shiftKey && eventMatchesLetter(e, 't')) {
    createShortcutTab();
    e.preventDefault();
    return true;
  }
  if (!e.shiftKey && eventMatchesLetter(e, 'w')) {
    closeActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && e.key === 'ArrowRight') {
    activateRelativeTab(1);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && e.key === 'ArrowLeft') {
    activateRelativeTab(-1);
    e.preventDefault();
    return true;
  }
  if (e.key === 'Tab') {
    activateRelativeTab(e.shiftKey ? -1 : 1);
    e.preventDefault();
    return true;
  }
  const matchedDigit = [1, 2, 3, 4, 5, 6, 7, 8, 9].find(digit => eventMatchesDigit(e, digit));
  if (matchedDigit) {
    const tabIndex = matchedDigit - 1;
    if (tabs[tabIndex]) activateTab(tabs[tabIndex].id);
    e.preventDefault();
    return true;
  }
  return false;
}

function handleActionShortcut(e) {
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, 'p')) {
    permalinkActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, 'c')) {
    copyActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === 'l' || e.key === 'L')) {
    clearActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === 'd' || e.key === 'D')) {
    closeActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  return false;
}

// Desktop chrome shortcuts (rail, search, history, options, theme, workflows,
// Files, projects, command registry, and Status Monitor).
// The composer is allowed to pass through so prompt-focused users can still
// trigger chrome toggles — each branch calls preventDefault so Option-glyphs
// (`«`, `˙`, `µ`, `©`, `≤`, `ˇ`, `ß`) never leak into the prompt on macOS.
// Other editable targets (modal inputs, search field, options textarea)
// remain gated so typing isn't hijacked.
//
// Search is bound to Alt+S (not Alt+F) because the composer owns Alt+F as
// readline word-forward; binding search to Alt+F would either hijack that
// or require a context-dependent chord that's a net UX loss. Alt+S has no
// readline conflict and works identically from everywhere.
//
// Each chord toggles its surface directly so the shortcut behavior stays in
// sync with the current rail/menu surfaces.
function handleChromeShortcut(e) {
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  // Alt+Shift+T → theme; guard first so it doesn't match Alt+Shift letter = T as tab-new.
  if (e.shiftKey && eventMatchesLetter(e, 't')) {
    if (typeof isThemeOverlayOpen === 'function' && isThemeOverlayOpen()) closeThemeSelector();
    else openThemeSelector();
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && eventMatchesLetter(e, 'f')) {
    if (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen()) {
      if (typeof closeWorkspace === 'function') closeWorkspace();
      else if (typeof hideWorkspaceOverlay === 'function') hideWorkspaceOverlay();
    } else if (typeof openWorkspace === 'function') {
      openWorkspace();
    }
    e.preventDefault();
    return true;
  }
  // All remaining chrome chords are shift-free.
  if (e.shiftKey) return false;
  if (eventMatchesLetter(e, 'm')) {
    if (isStatusMonitorShortcutOpen() && typeof closeStatusMonitor === 'function') closeStatusMonitor();
    else if (typeof openStatusMonitor === 'function') void openStatusMonitor({ source: 'shortcut' });
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'c')) {
    if (
      typeof isCommandRegistryOverlayOpen === 'function'
      && isCommandRegistryOverlayOpen()
      && typeof closeCommandRegistry === 'function'
    ) closeCommandRegistry();
    else if (typeof openCommandRegistry === 'function') openCommandRegistry();
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'p')) {
    if (
      typeof isProjectWorkspaceOpen === 'function'
      && isProjectWorkspaceOpen()
      && typeof closeProjectWorkspace === 'function'
    ) closeProjectWorkspace();
    else if (typeof openProjectWorkspace === 'function') void openProjectWorkspace();
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'h')) {
    if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen()) {
      hideHistoryPanel();
    } else if (typeof toggleHistoryPanelSurface === 'function') {
      toggleHistoryPanelSurface(true);
    }
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'g')) {
    if (typeof isWorkflowsOverlayOpen === 'function' && isWorkflowsOverlayOpen()) closeWorkflows();
    else openWorkflows();
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 's')) {
    document.getElementById('search-toggle-btn')?.click();
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Comma') || e.key === ',') {
    if (typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen()) closeOptions();
    else openOptions();
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Backslash') || e.key === '\\') {
    if (typeof toggleRailCollapsed === 'function') toggleRailCollapsed();
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Slash') || e.key === '/' || e.key === '÷') {
    if (typeof isFaqOverlayOpen === 'function' && isFaqOverlayOpen()) closeFaq();
    else openFaq();
    e.preventDefault();
    return true;
  }
  return false;
}
