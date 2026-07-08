// Lightweight Findings Board API. The full board controller loads only when opened.
import { loadFindingsBoard as importedLoadFindingsBoard } from '../../core/lazy_assets.js';

let loadedBoard = null;
let loadingBoard = null;

function boardFromModule(moduleApi) {
  if (moduleApi && typeof moduleApi.openFindingsBoard === 'function') return moduleApi;
  return null;
}

async function loadFindingsBoardController() {
  if (loadedBoard) return loadedBoard;
  if (!loadingBoard) {
    loadingBoard = Promise.resolve()
      .then(() => importedLoadFindingsBoard())
      .then((moduleApi) => {
        loadedBoard = boardFromModule(moduleApi);
        return loadedBoard;
      })
      .finally(() => {
        loadingBoard = null;
      });
  }
  return loadingBoard;
}

async function openFindingsBoard(options = {}) {
  const board = await loadFindingsBoardController();
  if (!board || typeof board.openFindingsBoard !== 'function') {
    throw new Error('Findings Board is not available.');
  }
  return board.openFindingsBoard(options);
}

function closeFindingsBoard(options = {}) {
  if (loadedBoard && typeof loadedBoard.closeFindingsBoard === 'function') {
    return loadedBoard.closeFindingsBoard(options);
  }
  const overlay = document.getElementById('findings-board-overlay');
  if (!overlay) return false;
  overlay.classList.add('u-hidden');
  overlay.classList.remove('open');
  overlay.setAttribute('aria-hidden', 'true');
  return true;
}

function isFindingsBoardOpen() {
  if (loadedBoard && typeof loadedBoard.isFindingsBoardOpen === 'function') {
    return loadedBoard.isFindingsBoardOpen();
  }
  return !!document.getElementById('findings-board-overlay')?.classList.contains('open');
}

const DarklabFindingsBoard = {
  close: closeFindingsBoard,
  isOpen: isFindingsBoardOpen,
  load: loadFindingsBoardController,
  open: openFindingsBoard,
};

export {
  DarklabFindingsBoard,
  closeFindingsBoard,
  isFindingsBoardOpen,
  loadFindingsBoardController,
  openFindingsBoard,
};
