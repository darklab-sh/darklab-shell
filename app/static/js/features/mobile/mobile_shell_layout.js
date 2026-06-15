import {
  acDropdown,
  cmdInput,
  commandRegistryOverlay,
  faqOverlay,
  hamburgerBtn,
  headerTitle,
  histRow,
  historyPanel,
  mobileComposerHost,
  mobileComposerRow,
  mobileHeaderActions,
  mobileMenu,
  mobileShell,
  mobileShellChrome,
  mobileShellOverlays,
  mobileShellTranscript,
  optionsOverlay,
  permalinkToast,
  runBtn,
  runTimer,
  searchBar,
  shellInputRow,
  shellPromptWrap,
  status,
  tabPanels,
  terminalBar,
  terminalWrap,
  themeOverlay,
  workflowsOverlay,
  workspaceEditorOverlay,
  workspaceOverlay,
  workspaceViewerOverlay,
} from '../../core/dom.js';
import {
  blurVisibleComposerInputIfMobile,
  getMobileKeyboardOffsetBaseline,
  getMobileViewportClosedHeight,
  getVisibleComposerInput,
  hideHistoryPanel,
  isHistoryPanelOpen,
  setVisibilityState,
  syncMobileComposerKeyboardState,
} from '../../ui/ui_helpers.js';
import { setMobileShellLayoutHandlers as importedSetMobileShellLayoutHandlers } from './mobile_shell_layout_bridge.js';

const MOBILE_SHELL_LAYOUT_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function useMobileTerminalViewportMode() {
  // Mobile mode depends on both width and input modality. A narrow desktop
  // browser window should not automatically switch into the mobile shell.
  if (typeof window === 'undefined') return false;
  const nav = window.navigator || (typeof navigator !== 'undefined' ? navigator : null);
  const touchPoints = nav ? (nav.maxTouchPoints || 0) : 0;
  const hasTouch = touchPoints > 0
    || (typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches);
  if (!hasTouch) return false;
  if (typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 900px)').matches) return true;
  return window.innerWidth <= 900;
}

const _shellInputRowHomeParent = typeof shellInputRow !== 'undefined' && shellInputRow ? shellInputRow.parentElement : null;
const _acDropdownHomeParent = typeof acDropdown !== 'undefined' && acDropdown ? acDropdown.parentElement : null;
const _histRowHomeParent = typeof histRow !== 'undefined' && histRow ? histRow.parentElement : null;
const _terminalBarHomeParent = typeof terminalBar !== 'undefined' && terminalBar ? terminalBar.parentElement : null;
const _searchBarHomeParent = typeof searchBar !== 'undefined' && searchBar ? searchBar.parentElement : null;
const _tabPanelsHomeParent = typeof tabPanels !== 'undefined' && tabPanels ? tabPanels.parentElement : null;
const _historyPanelHomeParent = typeof historyPanel !== 'undefined' && historyPanel ? historyPanel.parentElement : null;
const _permalinkToastHomeParent = typeof permalinkToast !== 'undefined' && permalinkToast ? permalinkToast.parentElement : null;
const _confirmHostEl = document.getElementById('confirm-host');
const _confirmHostHomeParent = _confirmHostEl ? _confirmHostEl.parentElement : null;
const _workflowsOverlayHomeParent = typeof workflowsOverlay !== 'undefined' && workflowsOverlay ? workflowsOverlay.parentElement : null;
const _schedulesOverlayEl = document.getElementById('schedules-overlay');
const _schedulesOverlayHomeParent = _schedulesOverlayEl ? _schedulesOverlayEl.parentElement : null;
const _workspaceOverlayHomeParent = typeof workspaceOverlay !== 'undefined' && workspaceOverlay ? workspaceOverlay.parentElement : null;
const _faqOverlayHomeParent = typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay.parentElement : null;
const _commandRegistryOverlayHomeParent = typeof commandRegistryOverlay !== 'undefined' && commandRegistryOverlay ? commandRegistryOverlay.parentElement : null;
const _themeOverlayHomeParent = typeof themeOverlay !== 'undefined' && themeOverlay ? themeOverlay.parentElement : null;
const _optionsOverlayHomeParent = typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay.parentElement : null;
const _statusHomeParent = typeof status !== 'undefined' && status ? status.parentElement : null;
const _runTimerHomeParent = typeof runTimer !== 'undefined' && runTimer ? runTimer.parentElement : null;
const _headerHomeParent = typeof headerTitle !== 'undefined' && headerTitle ? headerTitle.closest('header') : (typeof document !== 'undefined' ? document.querySelector('header') : null);
const _mobileHeaderActionsHomeParent = typeof mobileHeaderActions !== 'undefined' && mobileHeaderActions ? mobileHeaderActions : _headerHomeParent;

function _moveComposerNode(node, target, anchor = null) {
  if (!node || !target || node.parentElement === target) return;
  if (anchor && anchor.parentElement === target) {
    target.insertBefore(node, anchor);
  } else {
    target.appendChild(node);
  }
}

function _syncShellNodeGroup(useMobile, target, specs) {
  if (!Array.isArray(specs) || !target) return;
  for (const spec of specs) {
    if (!spec || !spec.node) continue;
    if (useMobile) {
      _moveComposerNode(spec.node, target);
    } else if (spec.homeParent) {
      _moveComposerNode(spec.node, spec.homeParent, spec.desktopAnchor || null);
    }
  }
}

function _syncVisibilityGroup(useMobile, specs) {
  if (!Array.isArray(specs)) return;
  for (const spec of specs) {
    if (!spec || !spec.node) continue;
    const visible = useMobile ? spec.visibleOnMobile : spec.visibleOnDesktop;
    const ariaHidden = useMobile ? spec.ariaHiddenOnMobile : spec.ariaHiddenOnDesktop;
    if (typeof visible === 'boolean') {
      setVisibilityState(spec.node, !visible, ariaHidden);
    }
  }
}

function _getMobileUiLayoutRefs() {
  const shellRoot = typeof mobileShell !== 'undefined' && mobileShell ? mobileShell : null;
  const composerHost = typeof mobileComposerHost !== 'undefined' && mobileComposerHost ? mobileComposerHost : null;
  const composerRow = typeof mobileComposerRow !== 'undefined' && mobileComposerRow ? mobileComposerRow : null;
  if (!shellRoot && !composerHost && !composerRow) return null;
  return {
    shell: shellRoot ? {
      root: shellRoot,
      chromeMount: typeof mobileShellChrome !== 'undefined' && mobileShellChrome ? mobileShellChrome : shellRoot,
      transcriptMount: typeof mobileShellTranscript !== 'undefined' && mobileShellTranscript ? mobileShellTranscript : shellRoot,
      overlaysMount: typeof mobileShellOverlays !== 'undefined' && mobileShellOverlays ? mobileShellOverlays : shellRoot,
    } : null,
    composer: {
      host: composerHost,
      row: composerRow,
    },
  };
}

// These refs let the same DOM nodes move between the desktop document flow and
// the simplified mobile shell without duplicating markup or event handlers.
const _mobileUiLayoutRefs = _getMobileUiLayoutRefs();
const _workspaceOverlayEl = typeof workspaceOverlay !== 'undefined' && workspaceOverlay ? workspaceOverlay : null;
const _uiOverlayRefs = {
  mobileMenu: mobileMenu || null,
  hamburgerBtn: hamburgerBtn || null,
  workflowsOverlay: typeof workflowsOverlay !== 'undefined' && workflowsOverlay ? workflowsOverlay : null,
  schedulesOverlay: _schedulesOverlayEl,
  workspaceOverlay: _workspaceOverlayEl,
  workspaceViewerOverlay: typeof workspaceViewerOverlay !== 'undefined' && workspaceViewerOverlay ? workspaceViewerOverlay : null,
  workspaceEditorOverlay: typeof workspaceEditorOverlay !== 'undefined' && workspaceEditorOverlay ? workspaceEditorOverlay : null,
  faqOverlay: typeof faqOverlay !== 'undefined' && faqOverlay ? faqOverlay : null,
  commandRegistryOverlay: typeof commandRegistryOverlay !== 'undefined' && commandRegistryOverlay ? commandRegistryOverlay : null,
  themeOverlay: typeof themeOverlay !== 'undefined' && themeOverlay ? themeOverlay : null,
  optionsOverlay: typeof optionsOverlay !== 'undefined' && optionsOverlay ? optionsOverlay : null,
  historyPanel: typeof historyPanel !== 'undefined' && historyPanel ? historyPanel : null,
};

function _bindMobileComposerInteractions(uiRefs) {
  const composerRefs = uiRefs && uiRefs.composer;
  if (!composerRefs || !composerRefs.host || !cmdInput) return;
}

const _mobileShellChromeNodes = [
  { node: histRow, homeParent: _histRowHomeParent, desktopAnchor: terminalBar || null },
  { node: terminalBar, homeParent: _terminalBarHomeParent, desktopAnchor: searchBar || null },
  { node: searchBar, homeParent: _searchBarHomeParent, desktopAnchor: tabPanels || null },
];
const _mobileShellTranscriptNodes = [
  { node: tabPanels, homeParent: _tabPanelsHomeParent, desktopAnchor: mobileComposerHost || null },
];
const _mobileShellOverlayNodes = [
  { node: historyPanel, homeParent: _historyPanelHomeParent, desktopAnchor: permalinkToast || null },
  { node: permalinkToast, homeParent: _permalinkToastHomeParent, desktopAnchor: _confirmHostEl || faqOverlay || null },
  { node: _confirmHostEl, homeParent: _confirmHostHomeParent, desktopAnchor: faqOverlay || null },
  { node: faqOverlay, homeParent: _faqOverlayHomeParent, desktopAnchor: commandRegistryOverlay || themeOverlay || null },
  { node: commandRegistryOverlay, homeParent: _commandRegistryOverlayHomeParent, desktopAnchor: themeOverlay || null },
  { node: themeOverlay, homeParent: _themeOverlayHomeParent, desktopAnchor: optionsOverlay || null },
  { node: optionsOverlay, homeParent: _optionsOverlayHomeParent, desktopAnchor: _workspaceOverlayEl || workflowsOverlay || null },
  { node: _workspaceOverlayEl, homeParent: _workspaceOverlayHomeParent, desktopAnchor: workflowsOverlay || null },
  { node: workflowsOverlay, homeParent: _workflowsOverlayHomeParent, desktopAnchor: _schedulesOverlayEl || null },
  { node: _schedulesOverlayEl, homeParent: _schedulesOverlayHomeParent, desktopAnchor: null },
];

function syncMobileShellChromeLayout(useMobile, mobileShellChromeMount) {
  _syncShellNodeGroup(useMobile, mobileShellChromeMount, _mobileShellChromeNodes);
}

function syncMobileShellTranscriptLayout(useMobile, mobileShellTranscriptMount, mobileShellChromeMount) {
  _syncShellNodeGroup(useMobile, mobileShellTranscriptMount || mobileShellChromeMount, _mobileShellTranscriptNodes);
}

function syncMobileShellOverlayLayout(useMobile, mobileShellOverlaysMount) {
  _syncShellNodeGroup(useMobile, mobileShellOverlaysMount, _mobileShellOverlayNodes);
}

function syncMobileShellLayout(mobileMode) {
  // The mobile shell is mostly a re-parenting operation: move the same chrome,
  // transcript, and overlays into mobile mounts instead of rendering variants.
  if (typeof document === 'undefined') return;
  const useMobile = !!mobileMode;
  const mobileShellRefs = _mobileUiLayoutRefs && _mobileUiLayoutRefs.shell;
  const mobileShellRoot = mobileShellRefs && mobileShellRefs.root;
  const desktopShell = typeof terminalWrap !== 'undefined' && terminalWrap ? terminalWrap : null;
  if (mobileShellRoot) {
    setVisibilityState(mobileShellRoot, !useMobile, useMobile ? 'false' : 'true');
  }
  if (desktopShell) {
    setVisibilityState(desktopShell, useMobile, useMobile ? 'true' : 'false');
  }
  if (!mobileShellRefs) return;
  const mobileShellChromeMount = mobileShellRefs.chromeMount;
  const mobileShellOverlaysMount = mobileShellRefs.overlaysMount;
  const mobileShellTranscriptMount = mobileShellRefs.transcriptMount || mobileShellChromeMount;
  syncMobileShellChromeLayout(useMobile, mobileShellChromeMount);
  syncMobileShellTranscriptLayout(useMobile, mobileShellTranscriptMount, mobileShellChromeMount);
  syncMobileShellOverlayLayout(useMobile, mobileShellOverlaysMount);
  if (status && _headerHomeParent) {
    if (useMobile) _moveComposerNode(status, _mobileHeaderActionsHomeParent, hamburgerBtn || null);
    else _moveComposerNode(status, _statusHomeParent);
  }
  if (runTimer && _headerHomeParent) {
    if (useMobile) _moveComposerNode(runTimer, _mobileHeaderActionsHomeParent, hamburgerBtn || null);
    else _moveComposerNode(runTimer, _runTimerHomeParent);
  }
  if (!useMobile && _shellInputRowHomeParent) _moveComposerNode(shellInputRow, _shellInputRowHomeParent);
}

function syncMobileComposerLayout(mobileMode) {
  if (typeof document === 'undefined') return;
  const useMobile = !!mobileMode;
  const mobileComposerRefs = _mobileUiLayoutRefs && _mobileUiLayoutRefs.composer;
  _syncVisibilityGroup(useMobile, [
    { node: mobileComposerRefs.host, visibleOnMobile: true, visibleOnDesktop: false, ariaHiddenOnMobile: 'false', ariaHiddenOnDesktop: 'true' },
    { node: shellPromptWrap, visibleOnMobile: false, visibleOnDesktop: true, ariaHiddenOnMobile: 'true', ariaHiddenOnDesktop: 'false' },
    { node: mobileComposerRefs.row, visibleOnMobile: true, visibleOnDesktop: false, ariaHiddenOnMobile: 'false', ariaHiddenOnDesktop: 'true' },
    { node: runBtn, visibleOnMobile: false, visibleOnDesktop: false, ariaHiddenOnMobile: 'true', ariaHiddenOnDesktop: 'true' },
    { node: shellInputRow, visibleOnMobile: false, visibleOnDesktop: true, ariaHiddenOnMobile: 'true', ariaHiddenOnDesktop: 'true' },
  ]);
  if (useMobile) {
    _moveComposerNode(acDropdown, mobileComposerRefs.host, mobileComposerRefs.host.firstElementChild || null);
  } else {
    if (typeof shellInputRow !== 'undefined' && shellInputRow && _shellInputRowHomeParent) {
      _moveComposerNode(shellInputRow, _shellInputRowHomeParent);
    }
    if (typeof acDropdown !== 'undefined' && acDropdown && _acDropdownHomeParent) {
      _moveComposerNode(acDropdown, _acDropdownHomeParent, shellInputRow || null);
    }
  }
}

function isChromeIOS() {
  if (typeof navigator === 'undefined') return false;
  return /CriOS/i.test(navigator.userAgent || '');
}

function getMobileKeyboardOffset() {
  const isMobileMode = typeof window.useMobileTerminalViewportMode === 'function'
    ? window.useMobileTerminalViewportMode()
    : useMobileTerminalViewportMode();
  if (!isMobileMode || !window.visualViewport) return 0;
  const liveInnerHeight = Math.round(window.innerHeight || 0);
  const visualHeight = Math.round(window.visualViewport.height || 0);
  const offsetTop = Math.round(window.visualViewport.offsetTop || 0);
  const closedHeight = typeof getMobileViewportClosedHeight === 'function'
    ? getMobileViewportClosedHeight()
    : null;
  const baselineHeight = typeof closedHeight === 'number' && closedHeight > 0
    ? Math.max(closedHeight, liveInnerHeight)
    : liveInnerHeight;
  return Math.max(0, baselineHeight - visualHeight - offsetTop);
}

function isMobileKeyboardOpen(offset = null) {
  const isMobileMode = typeof window.useMobileTerminalViewportMode === 'function'
    ? window.useMobileTerminalViewportMode()
    : useMobileTerminalViewportMode();
  if (!isMobileMode) return false;
  const mobileInputEl = (typeof getVisibleComposerInput === 'function' && getVisibleComposerInput()) || null;
  const mobileInputFocused = !!(mobileInputEl && typeof document !== 'undefined' && document.activeElement === mobileInputEl);
  if (!mobileInputFocused) return false;
  const keyboardMarkedOpen = !!(
    typeof document !== 'undefined'
    && document.body
    && document.body.classList
    && document.body.classList.contains('mobile-keyboard-open')
  );
  if (keyboardMarkedOpen) return true;
  const keyboardBaseline = typeof getMobileKeyboardOffsetBaseline === 'function'
    ? getMobileKeyboardOffsetBaseline()
    : null;
  const baseline = typeof keyboardBaseline === 'number' ? keyboardBaseline : 0;
  if (typeof offset === 'number') return offset > baseline + 40;
  return true;
}

function syncMobileViewportState() {
  if (typeof document === 'undefined') return;
  const mobileMode = typeof window.useMobileTerminalViewportMode === 'function'
    ? window.useMobileTerminalViewportMode()
    : useMobileTerminalViewportMode();
  const hasMobileShell = !!(_mobileUiLayoutRefs && _mobileUiLayoutRefs.shell);
  const activeMobileMode = mobileMode && hasMobileShell;
  const keyboardOffset = typeof window.getMobileKeyboardOffset === 'function'
    ? window.getMobileKeyboardOffset()
    : getMobileKeyboardOffset();
  const keyboardOpen = typeof window.isMobileKeyboardOpen === 'function'
    ? window.isMobileKeyboardOpen(keyboardOffset)
    : isMobileKeyboardOpen(keyboardOffset);
  const wasMobileKeyboardOpen = document.body.classList.contains('mobile-keyboard-open');
  const wasMobileTerminalMode = document.body.classList.contains('mobile-terminal-mode');
  if (!hasMobileShell) return;
  document.body.classList.toggle('mobile-terminal-mode', activeMobileMode);
  if (wasMobileTerminalMode !== activeMobileMode && typeof document.dispatchEvent === 'function') {
    document.dispatchEvent(new CustomEvent('app:mobile-terminal-mode-changed', {
      detail: { active: activeMobileMode },
    }));
  }
  document.body.classList.toggle('mobile-chrome-ios', activeMobileMode && isChromeIOS());
  if (typeof syncMobileComposerKeyboardState === 'function') {
    syncMobileComposerKeyboardState(keyboardOffset, {
      active: activeMobileMode,
      open: activeMobileMode && keyboardOpen,
    });
  }
  else document.body.classList.toggle('mobile-keyboard-open', activeMobileMode && keyboardOpen);
  syncMobileShellLayout(activeMobileMode);
  syncMobileComposerLayout(activeMobileMode);
  if (activeMobileMode) MOBILE_SHELL_LAYOUT_GLOBAL.syncMobileViewportHeight?.({ keyboardOpen });
  if (activeMobileMode && keyboardOpen) {
    MOBILE_SHELL_LAYOUT_GLOBAL.queueMobileOutputTailRefresh?.({ keyboardOpen: true, delays: [0] });
  } else if (activeMobileMode && wasMobileKeyboardOpen) {
    MOBILE_SHELL_LAYOUT_GLOBAL.queueMobileOutputTailRefresh?.({ keyboardOpen: false });
  }
  if (activeMobileMode && keyboardOpen) {
    MOBILE_SHELL_LAYOUT_GLOBAL.hideMobileMenu?.();
    if (isHistoryPanelOpen()) hideHistoryPanel();
    // Hide autocomplete only when the mobile keyboard becomes active.
    if (!wasMobileKeyboardOpen) MOBILE_SHELL_LAYOUT_GLOBAL.acHide?.();
  }
}

function dismissMobileKeyboardAfterSubmit() {
  const isMobileMode = typeof window.useMobileTerminalViewportMode === 'function'
    ? window.useMobileTerminalViewportMode()
    : useMobileTerminalViewportMode();
  if (!isMobileMode) return;
  if (typeof blurVisibleComposerInputIfMobile === 'function') {
    setTimeout(() => blurVisibleComposerInputIfMobile(), 0);
  }
}

if (typeof window !== 'undefined') {
  if (typeof importedSetMobileShellLayoutHandlers === 'function') {
    importedSetMobileShellLayoutHandlers({
    dismissMobileKeyboardAfterSubmit,
    getMobileKeyboardOffset,
    isMobileKeyboardOpen,
    syncMobileViewportState,
    useMobileTerminalViewportMode,
    });
  }
}

export {
  _bindMobileComposerInteractions,
  _mobileUiLayoutRefs,
  _uiOverlayRefs,
  dismissMobileKeyboardAfterSubmit,
  getMobileKeyboardOffset,
  isChromeIOS,
  isMobileKeyboardOpen,
  syncMobileComposerLayout,
  syncMobileShellChromeLayout,
  syncMobileShellLayout,
  syncMobileShellOverlayLayout,
  syncMobileShellTranscriptLayout,
  syncMobileViewportState,
  useMobileTerminalViewportMode,
};
