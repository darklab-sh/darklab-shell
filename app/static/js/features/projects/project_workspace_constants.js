// Shared Project workspace constants.
// Loaded before shell_chrome.js so controller composition can pass these values around.

(function projectWorkspaceConstantsModule(global) {
  'use strict';

  const findingReviewStates = [
    { value: 'new', label: 'New' },
    { value: 'reviewed', label: 'Reviewed' },
    { value: 'important', label: 'Important' },
    { value: 'false_positive', label: 'False positive' },
    { value: 'needs_followup', label: 'Follow-up' },
  ];

  const findingSeverityRank = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
    info: 4,
  };

  global.DarklabProjectWorkspaceConstants = {
    fieldSavedIndicatorDelayMs: 200,
    fieldSavedIndicatorVisibleMs: 1600,
    findingNoteStateOptions: [
      { value: 'all', label: 'All notes' },
      { value: 'noted', label: 'With notes' },
      { value: 'unnoted', label: 'Without notes' },
    ],
    findingOrphanOptions: [
      { value: 'hide', label: 'Hide orphans' },
      { value: 'all', label: 'Show all' },
      { value: 'only', label: 'Only orphans' },
    ],
    findingReviewRank: findingReviewStates.reduce((acc, state, index) => {
      acc[state.value] = index;
      return acc;
    }, {}),
    findingReviewStates,
    findingSeverityRank,
    findingSortOptions: [
      { value: 'source', label: 'Source order' },
      { value: 'run', label: 'Run' },
      { value: 'severity', label: 'Severity' },
      { value: 'review', label: 'Review state' },
      { value: 'target', label: 'Target' },
      { value: 'newest', label: 'Newest run' },
    ],
    mobileNotePreviewLimit: 100,
    projectLabelsSavedVisibleMs: 2000,
    projectNotesAutosaveDelayMs: 450,
    workspaceBroadcastKey: 'darklab_project_workspace_changed',
  };
})(globalThis);
