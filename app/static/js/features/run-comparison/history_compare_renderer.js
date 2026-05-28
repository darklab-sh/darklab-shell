// ── Run comparison result renderer ─────────────────────────────────────
// Transcript hunk rendering, object diff sections, restore actions, and compare fetch flow.

function _compareMetricCell(label, value, tone = '') {
  const cell = document.createElement('div');
  cell.className = `history-compare-metric${tone ? ` ${tone}` : ''}`;
  const labelEl = document.createElement('div');
  labelEl.className = 'history-compare-metric-label';
  labelEl.textContent = label;
  const valueEl = document.createElement('div');
  valueEl.className = 'history-compare-metric-value';
  valueEl.textContent = value;
  cell.appendChild(labelEl);
  cell.appendChild(valueEl);
  return cell;
}

function _appendHistoryCompareSegments(parent, segments, fallbackText) {
  const safeSegments = Array.isArray(segments) ? segments : [];
  if (!safeSegments.length) {
    parent.textContent = fallbackText || '';
    return;
  }
  safeSegments.forEach(segment => {
    const span = document.createElement('span');
    span.textContent = segment && typeof segment.text === 'string' ? segment.text : '';
    if (segment && segment.changed) span.className = 'history-compare-line-delta';
    parent.appendChild(span);
  });
}

function _renderHistoryCompareLineText(line, segments = null, limits = {}) {
  const code = document.createElement('code');
  const rawText = String((line && line.text) || '');
  const limit = _historyCompareLineLimit(limits);
  const truncated = rawText.length > limit;
  const visibleText = truncated ? rawText.slice(0, limit) : rawText;
  const safeSegments = Array.isArray(segments) ? segments : [];
  if (safeSegments.length && !truncated) {
    _appendHistoryCompareSegments(code, safeSegments, rawText);
  } else {
    code.textContent = visibleText;
  }
  if (truncated) {
    const expander = document.createElement('button');
    expander.type = 'button';
    expander.className = 'chip chip-action history-compare-line-expander';
    expander.textContent = `... +${(rawText.length - limit).toLocaleString()} chars`;
    expander.addEventListener('click', event => {
      event.stopPropagation();
      const split = expander.closest?.('.history-compare-split');
      code.textContent = rawText;
      expander.remove();
      _scheduleHistoryCompareRowPairHeightSync(split);
    });
    const wrap = document.createElement('span');
    wrap.className = 'history-compare-line-text-wrap';
    wrap.appendChild(code);
    wrap.appendChild(expander);
    return wrap;
  }
  return code;
}

function _renderHistoryComparePaneRow(line, {
  sideLabel = '',
  signClass = '',
  rowClass = '',
  segments = null,
  limits = {},
  side = '',
  compareLineIndex = null,
  anchorItems = [],
} = {}) {
  const row = document.createElement('div');
  row.className = `history-compare-row${rowClass ? ` ${rowClass}` : ''}`;
  if (side) row.dataset.side = side;
  if (Number.isFinite(compareLineIndex)) row.dataset.compareLineIndex = String(compareLineIndex);
  if (line && line.kind) row.dataset.compareKind = String(line.kind);
  if (line && line.role) row.dataset.compareRole = String(line.role);
  const mark = document.createElement('span');
  mark.className = `history-compare-line-mark${signClass ? ` ${signClass}` : ''}`;
  mark.textContent = sideLabel;
  row.appendChild(mark);
  const anchorSlot = document.createElement('span');
  anchorSlot.className = 'history-compare-line-anchor-slot';
  const safeAnchors = Array.isArray(anchorItems) ? anchorItems : [];
  if (safeAnchors.length && Number.isFinite(compareLineIndex)) {
    const marker = document.createElement('button');
    marker.type = 'button';
    marker.className = `btn btn-ghost history-compare-finding-marker is-${_historyCompareAnchorTone(safeAnchors)}`;
    marker.setAttribute('aria-label', 'Jump to linked finding');
    marker.addEventListener('click', event => {
      event.stopPropagation();
      const findingRow = document.querySelector(
        `.history-compare-object-row[data-object-kind="finding"][data-compare-side="${side}"][data-compare-line-index="${_historyCompareCssEscape(compareLineIndex)}"]`,
      );
      if (typeof findingRow?.scrollIntoView === 'function') {
        findingRow.scrollIntoView({ block: 'center', inline: 'nearest' });
      }
      if (findingRow) {
        findingRow.classList.remove('history-compare-line-pulse');
        void findingRow.offsetWidth;
        findingRow.classList.add('history-compare-line-pulse');
        setTimeout(() => findingRow.classList.remove('history-compare-line-pulse'), 900);
      }
    });
    anchorSlot.appendChild(marker);
  }
  row.appendChild(anchorSlot);
  row.appendChild(_renderHistoryCompareLineText(line, segments, limits));
  return row;
}

function _renderHistoryCompareSpacer(label = '') {
  const row = document.createElement('div');
  row.className = 'history-compare-row history-compare-row-spacer';
  row.setAttribute('aria-hidden', 'true');
  const mark = document.createElement('span');
  mark.textContent = label;
  row.appendChild(mark);
  row.appendChild(document.createElement('span'));
  row.appendChild(document.createElement('span'));
  return row;
}

function _historyCompareRowHeight(row) {
  if (!row) return 0;
  const rect = typeof row.getBoundingClientRect === 'function' ? row.getBoundingClientRect() : null;
  return Math.ceil(Math.max(Number(rect?.height || 0), Number(row.offsetHeight || 0)));
}

function _historyCompareUsesStackedMobilePanes(wrap) {
  const mobile = typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode();
  const stacked = wrap?.classList?.contains('is-unified') || wrap?.classList?.contains('is-changes-only');
  return Boolean(mobile && stacked);
}

function _clearHistoryCompareRowPairHeights(wrap) {
  wrap?.querySelectorAll?.('.history-compare-row[data-compare-pair]').forEach(row => {
    row.style.minHeight = '';
  });
}

function _syncHistoryCompareRowPairHeights(wrap) {
  if (!wrap || !wrap.isConnected) return;
  if (_historyCompareUsesStackedMobilePanes(wrap)) {
    _clearHistoryCompareRowPairHeights(wrap);
    return;
  }
  const pairs = new Map();
  wrap.querySelectorAll('.history-compare-row[data-compare-pair]').forEach(row => {
    row.style.minHeight = '';
    const key = row.dataset.comparePair || '';
    if (!key) return;
    const rows = pairs.get(key) || [];
    rows.push(row);
    pairs.set(key, rows);
  });
  pairs.forEach(rows => {
    if (rows.length < 2) return;
    const height = Math.max(...rows.map(_historyCompareRowHeight));
    if (!height) return;
    rows.forEach(row => {
      row.style.minHeight = `${height}px`;
    });
  });
}

function _scheduleHistoryCompareRowPairHeightSync(wrap) {
  if (!wrap) return;
  if (_historyCompareRowHeightFrame !== null) {
    const cancel = typeof cancelAnimationFrame === 'function' ? cancelAnimationFrame : clearTimeout;
    cancel(_historyCompareRowHeightFrame);
  }
  const raf = typeof requestAnimationFrame === 'function' ? requestAnimationFrame : callback => setTimeout(callback, 0);
  _historyCompareRowHeightFrame = raf(() => {
    _historyCompareRowHeightFrame = null;
    _syncHistoryCompareRowPairHeights(wrap);
  });
}

function _bindHistoryCompareRowPairHeightSync(wrap) {
  if (_historyCompareRowResizeObserver) {
    _historyCompareRowResizeObserver.disconnect();
    _historyCompareRowResizeObserver = null;
  }
  if (typeof ResizeObserver === 'function' && wrap) {
    _historyCompareRowResizeObserver = new ResizeObserver(() => _scheduleHistoryCompareRowPairHeightSync(wrap));
    _historyCompareRowResizeObserver.observe(wrap);
  }
  _scheduleHistoryCompareRowPairHeightSync(wrap);
}

function _appendHistoryCompareRowPair(leftPane, rightPane, leftRow, rightRow, unitTone = '') {
  const pair = String(_historyCompareRowPairSequence);
  _historyCompareRowPairSequence += 1;
  leftRow.dataset.comparePair = pair;
  rightRow.dataset.comparePair = pair;
  if (unitTone) {
    const unit = String(_historyCompareUnitSequence);
    _historyCompareUnitSequence += 1;
    leftRow.dataset.compareUnitIndex = unit;
    rightRow.dataset.compareUnitIndex = unit;
    leftRow.dataset.compareUnitTone = unitTone;
    rightRow.dataset.compareUnitTone = unitTone;
  }
  leftPane.appendChild(leftRow);
  rightPane.appendChild(rightRow);
}

function _advanceHistoryCompareUnits(count) {
  _historyCompareUnitSequence += Math.max(0, Number(count || 0));
}

function _historyCompareReplaceRenderEvents(hunk) {
  const events = [];
  (hunk.changed_pairs || []).forEach(pair => {
    events.push({
      type: 'pair',
      leftIndex: Number(pair.left_index),
      rightIndex: Number(pair.right_index),
      pair,
    });
  });
  (hunk.left_unpaired || []).forEach(index => {
    events.push({ type: 'left', leftIndex: Number(index), rightIndex: null });
  });
  (hunk.right_unpaired || []).forEach(index => {
    events.push({ type: 'right', leftIndex: null, rightIndex: Number(index) });
  });

  const pending = events.filter(event => (
    (event.leftIndex === null || Number.isFinite(event.leftIndex))
    && (event.rightIndex === null || Number.isFinite(event.rightIndex))
  ));
  const ordered = [];
  const nextSideIndex = (side) => {
    const key = side === 'left' ? 'leftIndex' : 'rightIndex';
    const indexes = pending
      .map(event => event[key])
      .filter(index => Number.isFinite(index));
    return indexes.length ? Math.min(...indexes) : null;
  };
  while (pending.length) {
    const nextLeft = nextSideIndex('left');
    const nextRight = nextSideIndex('right');
    let index = pending.findIndex(event => (
      (event.leftIndex === null || event.leftIndex === nextLeft)
      && (event.rightIndex === null || event.rightIndex === nextRight)
    ));
    if (index < 0) {
      index = pending
        .map((event, eventIndex) => ({
          eventIndex,
          order: Math.max(
            Number.isFinite(event.leftIndex) ? event.leftIndex : -1,
            Number.isFinite(event.rightIndex) ? event.rightIndex : -1,
          ),
        }))
        .sort((a, b) => a.order - b.order || a.eventIndex - b.eventIndex)[0].eventIndex;
    }
    ordered.push(pending.splice(index, 1)[0]);
  }
  return ordered;
}

function _historyCompareFoldRange(hunk, side) {
  const context = hunk && hunk.context ? hunk.context : {};
  const leading = context.leading && Array.isArray(context.leading[side]) ? context.leading[side] : [];
  const trailing = context.trailing && Array.isArray(context.trailing[side]) ? context.trailing[side] : [];
  const bounds = hunk && hunk[side] ? hunk[side] : {};
  return {
    start: Number(bounds.start || 0) + leading.length,
    end: Math.max(Number(bounds.start || 0) + leading.length, Number(bounds.end || 0) - trailing.length),
  };
}

function _historyCompareLineUrl(data, side, start, end) {
  const params = new URLSearchParams();
  params.set('left', data.left_run_id || data.left?.id || '');
  params.set('right', data.right_run_id || data.right?.id || '');
  params.set('side', side === 'left' ? 'a' : 'b');
  params.set('start', String(start));
  params.set('end', String(end));
  if (data.project_id) params.set('project_id', data.project_id);
  if (data.baseline_label) params.set('baseline_label', data.baseline_label);
  return `/history/compare/lines?${params.toString()}`;
}

function _fetchHistoryCompareFoldSide(data, hunk, side) {
  const range = _historyCompareFoldRange(hunk, side);
  if (range.start >= range.end) return Promise.resolve([]);
  const collected = [];
  const loadPage = start => apiFetch(_historyCompareLineUrl(data, side, start, range.end))
    .then(resp => resp.json())
    .then(payload => {
      if (payload.error) throw new Error(payload.error);
      const lines = Array.isArray(payload.lines) ? payload.lines : [];
      collected.push(...lines);
      const nextStart = Number(payload.end);
      if (
        payload.truncated
        && !payload.range_clamped
        && Number.isFinite(nextStart)
        && nextStart > start
        && nextStart < range.end
      ) {
        return loadPage(nextStart);
      }
      return collected;
    });
  return loadPage(range.start);
}

function _historyCompareSliceContextLines(lines, edge, contextLimit) {
  const safeLines = Array.isArray(lines) ? lines : [];
  if (contextLimit === null) return safeLines;
  const limit = Math.max(0, Number(contextLimit || 0));
  if (!limit) return [];
  return edge === 'leading' ? safeLines.slice(-limit) : safeLines.slice(0, limit);
}

function _appendHistoryCompareEqualHunk(leftPane, rightPane, hunk, data, rerender, anchorMap, options = {}) {
  const limits = data.limits || {};
  const contextLimit = Object.prototype.hasOwnProperty.call(options, 'contextLimit') ? options.contextLimit : 3;
  const changesOnly = !!options.changesOnly;
  const context = hunk.context || {};
  const appendLines = (leftLines, rightLines, leftStart = 0, rightStart = 0) => {
    const count = Math.max(leftLines.length, rightLines.length);
    for (let index = 0; index < count; index += 1) {
      const leftCompareIndex = Number(leftStart) + index;
      const rightCompareIndex = Number(rightStart) + index;
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        leftLines[index]
          ? _renderHistoryComparePaneRow(leftLines[index], {
              sideLabel: 'A',
              rowClass: 'is-equal',
              limits,
              side: 'a',
              compareLineIndex: leftCompareIndex,
              anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
            })
          : _renderHistoryCompareSpacer('A'),
        rightLines[index]
          ? _renderHistoryComparePaneRow(rightLines[index], {
              sideLabel: 'B',
              rowClass: 'is-equal',
              limits,
              side: 'b',
              compareLineIndex: rightCompareIndex,
              anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
            })
          : _renderHistoryCompareSpacer('B'),
        'equal',
      );
    }
  };
  const makeFoldRow = (button) => {
    const row = document.createElement('div');
    row.className = 'history-compare-row history-compare-row-fold';
    row.appendChild(document.createElement('span'));
    row.appendChild(document.createElement('span'));
    row.appendChild(button);
    return row;
  };
  const makeFoldButtonPair = (label, expand) => {
    const foldButtons = [];
    const setFoldButtons = (disabled, text) => {
      foldButtons.forEach(button => {
        button.disabled = disabled;
        button.textContent = text;
      });
    };
    const makeFoldButton = () => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-secondary btn-compact history-compare-fold';
      button.textContent = label;
      button.addEventListener('click', () => expand(setFoldButtons));
      foldButtons.push(button);
      return button;
    };
    _appendHistoryCompareRowPair(leftPane, rightPane, makeFoldRow(makeFoldButton()), makeFoldRow(makeFoldButton()));
  };
  if (Array.isArray(hunk.left?.lines) || Array.isArray(hunk.right?.lines)) {
    const leftLines = hunk.left?.lines || [];
    const rightLines = hunk.right?.lines || [];
    const leftStart = _historyCompareNumber(hunk.left?.start, 0);
    const rightStart = _historyCompareNumber(hunk.right?.start, 0);
    const total = Math.max(leftLines.length, rightLines.length);
    if (changesOnly) {
      _advanceHistoryCompareUnits(total);
    } else if (contextLimit === null || total <= contextLimit * 2) {
      appendLines(leftLines, rightLines, leftStart, rightStart);
    } else {
      const leadingCount = Math.max(0, contextLimit);
      const trailingCount = Math.max(0, contextLimit);
      appendLines(leftLines.slice(0, leadingCount), rightLines.slice(0, leadingCount), leftStart, rightStart);
      const omitted = Math.max(0, total - leadingCount - trailingCount);
      if (omitted > 0) {
        if (hunk._expanded) {
          makeFoldButtonPair('▾ Hide unchanged lines', () => {
            hunk._expanded = false;
            rerender();
          });
          appendLines(
            leftLines.slice(leadingCount, total - trailingCount),
            rightLines.slice(leadingCount, total - trailingCount),
            leftStart + leadingCount,
            rightStart + leadingCount,
          );
        } else {
          makeFoldButtonPair(`▸ Show ${omitted.toLocaleString()} unchanged line(s)`, () => {
            hunk._expanded = true;
            rerender();
          });
          _advanceHistoryCompareUnits(omitted);
        }
      }
      appendLines(
        leftLines.slice(total - trailingCount),
        rightLines.slice(total - trailingCount),
        leftStart + Math.max(leadingCount, total - trailingCount),
        rightStart + Math.max(leadingCount, total - trailingCount),
      );
    }
    return;
  }
  const leftStart = _historyCompareNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareNumber(hunk.right?.start, 0);
  const rawLeadingLeft = context.leading?.left || [];
  const rawLeadingRight = context.leading?.right || [];
  const rawTrailingLeft = context.trailing?.left || [];
  const rawTrailingRight = context.trailing?.right || [];
  const leadingLeft = changesOnly ? [] : _historyCompareSliceContextLines(rawLeadingLeft, 'leading', contextLimit);
  const leadingRight = changesOnly ? [] : _historyCompareSliceContextLines(rawLeadingRight, 'leading', contextLimit);
  const trailingLeft = changesOnly ? [] : _historyCompareSliceContextLines(rawTrailingLeft, 'trailing', contextLimit);
  const trailingRight = changesOnly ? [] : _historyCompareSliceContextLines(rawTrailingRight, 'trailing', contextLimit);
  appendLines(
    leadingLeft,
    leadingRight,
    leftStart + Math.max(0, rawLeadingLeft.length - leadingLeft.length),
    rightStart + Math.max(0, rawLeadingRight.length - leadingRight.length),
  );
  if (hunk._expanded) {
    const collapse = () => {
      hunk._expanded = false;
      rerender();
    };
    const makeCollapseButton = () => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-secondary btn-compact history-compare-fold';
      button.textContent = '▾ Hide unchanged lines';
      button.addEventListener('click', collapse);
      return button;
    };
    _appendHistoryCompareRowPair(leftPane, rightPane, makeFoldRow(makeCollapseButton()), makeFoldRow(makeCollapseButton()));
    appendLines(
      hunk._expandedLeft || [],
      hunk._expandedRight || [],
      leftStart + leadingLeft.length,
      rightStart + leadingRight.length,
    );
    _advanceHistoryCompareUnits(
      Number(context.omitted || 0) - Math.max(
        Array.isArray(hunk._expandedLeft) ? hunk._expandedLeft.length : 0,
        Array.isArray(hunk._expandedRight) ? hunk._expandedRight.length : 0,
      ),
    );
  } else if (Number(context.omitted || 0) > 0) {
    const label = `▸ Show ${Number(context.omitted).toLocaleString()} unchanged line(s)`;
    const expand = (setFoldButtons) => {
      if (hunk._loading) return;
      hunk._loading = true;
      setFoldButtons(true, 'Loading unchanged lines...');
      const leftPromise = hunk._expandedLeft
        ? Promise.resolve(hunk._expandedLeft)
        : _fetchHistoryCompareFoldSide(data, hunk, 'left');
      const rightPromise = hunk._expandedRight
        ? Promise.resolve(hunk._expandedRight)
        : _fetchHistoryCompareFoldSide(data, hunk, 'right');
      Promise.all([leftPromise, rightPromise])
        .then(([leftLines, rightLines]) => {
          hunk._expandedLeft = leftLines;
          hunk._expandedRight = rightLines;
          hunk._expanded = true;
          hunk._loading = false;
          rerender();
        })
        .catch(() => {
          hunk._loading = false;
          setFoldButtons(false, label);
          showToast('Failed to load unchanged lines', 'error');
        });
    };
    makeFoldButtonPair(label, expand);
    _advanceHistoryCompareUnits(context.omitted);
  }
  appendLines(
    trailingLeft,
    trailingRight,
    _historyCompareNumber(hunk.left?.end, leftStart) - trailingLeft.length,
    _historyCompareNumber(hunk.right?.end, rightStart) - trailingRight.length,
  );
}

function _appendHistoryCompareReplaceHunk(leftPane, rightPane, hunk, data, anchorMap) {
  const limits = data.limits || {};
  const leftLines = hunk.left?.lines || [];
  const rightLines = hunk.right?.lines || [];
  const leftStart = _historyCompareNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareNumber(hunk.right?.start, 0);
  _historyCompareReplaceRenderEvents(hunk).forEach(event => {
    if (event.type === 'pair') {
      const pair = event.pair || {};
      const leftLine = leftLines[pair.left_index] || {};
      const rightLine = rightLines[pair.right_index] || {};
      const segments = pair.segments || {};
      const leftCompareIndex = leftStart + Number(pair.left_index || 0);
      const rightCompareIndex = rightStart + Number(pair.right_index || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryComparePaneRow(leftLine, {
          sideLabel: 'A',
          signClass: 'history-compare-line-removed',
          rowClass: `is-replace${pair.structural_change ? ' is-structural-change' : ''}`,
          segments: segments.left,
          limits,
          side: 'a',
          compareLineIndex: leftCompareIndex,
          anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
        }),
        _renderHistoryComparePaneRow(rightLine, {
          sideLabel: 'B',
          signClass: 'history-compare-line-added',
          rowClass: `is-replace${pair.structural_change ? ' is-structural-change' : ''}`,
          segments: segments.right,
          limits,
          side: 'b',
          compareLineIndex: rightCompareIndex,
          anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
        }),
        'changed',
      );
    } else if (event.type === 'left') {
      const leftCompareIndex = leftStart + Number(event.leftIndex || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryComparePaneRow(leftLines[event.leftIndex] || {}, {
          sideLabel: '-',
          signClass: 'history-compare-line-removed',
          rowClass: 'is-delete',
          limits,
          side: 'a',
          compareLineIndex: leftCompareIndex,
          anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
        }),
        _renderHistoryCompareSpacer(),
        'removed',
      );
    } else if (event.type === 'right') {
      const rightCompareIndex = rightStart + Number(event.rightIndex || 0);
      _appendHistoryCompareRowPair(
        leftPane,
        rightPane,
        _renderHistoryCompareSpacer(),
        _renderHistoryComparePaneRow(rightLines[event.rightIndex] || {}, {
          sideLabel: '+',
          signClass: 'history-compare-line-added',
          rowClass: 'is-insert',
          limits,
          side: 'b',
          compareLineIndex: rightCompareIndex,
          anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
        }),
        'added',
      );
    }
  });
}

function _appendHistoryCompareOneSidedHunk(leftPane, rightPane, hunk, data, anchorMap) {
  const limits = data.limits || {};
  const op = hunk.op;
  const lines = op === 'insert' ? (hunk.right?.lines || []) : (hunk.left?.lines || []);
  const leftStart = _historyCompareNumber(hunk.left?.start, 0);
  const rightStart = _historyCompareNumber(hunk.right?.start, 0);
  lines.forEach((line, index) => {
    const leftCompareIndex = leftStart + index;
    const rightCompareIndex = rightStart + index;
    _appendHistoryCompareRowPair(
      leftPane,
      rightPane,
      op === 'delete'
        ? _renderHistoryComparePaneRow(line, {
            sideLabel: '-',
            signClass: 'history-compare-line-removed',
            rowClass: 'is-delete',
            limits,
            side: 'a',
            compareLineIndex: leftCompareIndex,
            anchorItems: anchorMap?.a?.get(leftCompareIndex) || [],
          })
        : _renderHistoryCompareSpacer(),
      op === 'insert'
        ? _renderHistoryComparePaneRow(line, {
            sideLabel: '+',
            signClass: 'history-compare-line-added',
            rowClass: 'is-insert',
            limits,
            side: 'b',
            compareLineIndex: rightCompareIndex,
            anchorItems: anchorMap?.b?.get(rightCompareIndex) || [],
          })
        : _renderHistoryCompareSpacer(),
      op === 'insert' ? 'added' : 'removed',
    );
  });
}

function _appendHistoryCompareOmittedRows(leftPane, rightPane, hunk) {
  const omitted = hunk.lines_omitted || {};
  if (!Number(omitted.total || 0)) return;
  const row = document.createElement('div');
  row.className = 'history-compare-row history-compare-row-omitted';
  row.textContent = `${Number(omitted.total).toLocaleString()} changed line(s) omitted in this block.`;
  _appendHistoryCompareRowPair(leftPane, rightPane, row.cloneNode(true), row);
}

function _renderHistoryCompareSplitPane(data, options = {}) {
  const viewMode = options.viewMode || 'side_by_side';
  const wrap = document.createElement('div');
  wrap.className = `history-compare-split is-${viewMode.replace(/_/g, '-')}`;
  wrap.dataset.compareViewMode = viewMode;
  const anchorMap = _historyCompareBuildAnchorMap(data);
  const leftPane = document.createElement('div');
  leftPane.className = 'history-compare-pane nice-scroll';
  leftPane.dataset.side = 'a';
  const rightPane = document.createElement('div');
  rightPane.className = 'history-compare-pane nice-scroll';
  rightPane.dataset.side = 'b';
  const renderPanes = () => {
    leftPane.replaceChildren();
    rightPane.replaceChildren();
    _historyCompareRowPairSequence = 0;
    _historyCompareUnitSequence = 0;
    const leftTitle = document.createElement('div');
    leftTitle.className = 'history-compare-pane-title';
    leftTitle.textContent = 'Run A';
    const rightTitle = document.createElement('div');
    rightTitle.className = 'history-compare-pane-title';
    rightTitle.textContent = 'Run B';
    leftPane.appendChild(leftTitle);
    rightPane.appendChild(rightTitle);
    (Array.isArray(data.hunks) ? data.hunks : []).forEach(hunk => {
      if (!hunk || !hunk.op) return;
      if (hunk.op === 'equal') {
        _appendHistoryCompareEqualHunk(leftPane, rightPane, hunk, data, renderPanes, anchorMap, {
          contextLimit: options.contextLimit,
          changesOnly: viewMode === 'changes_only',
        });
      }
      else if (hunk.op === 'replace') _appendHistoryCompareReplaceHunk(leftPane, rightPane, hunk, data, anchorMap);
      else if (hunk.op === 'insert' || hunk.op === 'delete') _appendHistoryCompareOneSidedHunk(leftPane, rightPane, hunk, data, anchorMap);
      _appendHistoryCompareOmittedRows(leftPane, rightPane, hunk);
    });
    if (Number(data.truncated?.hunks_omitted || 0) > 0) {
      const placeholder = document.createElement('div');
      placeholder.className = 'history-compare-row history-compare-row-omitted history-compare-surplus';
      placeholder.textContent = `${Number(data.truncated.hunks_omitted).toLocaleString()} additional changed hunk(s) omitted.`;
      _appendHistoryCompareRowPair(leftPane, rightPane, placeholder.cloneNode(true), placeholder);
    }
    _scheduleHistoryCompareRowPairHeightSync(wrap);
  };
  renderPanes();
  if (!(typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode())) {
    let syncing = false;
    const sync = (source, target) => {
      if (syncing || !source || !target) return;
      syncing = true;
      const raf = typeof requestAnimationFrame === 'function'
        ? requestAnimationFrame
        : callback => setTimeout(callback, 0);
      raf(() => {
        target.scrollTop = source.scrollTop;
        syncing = false;
      });
    };
    leftPane.addEventListener('scroll', () => sync(leftPane, rightPane));
    rightPane.addEventListener('scroll', () => sync(rightPane, leftPane));
  }
  wrap.appendChild(leftPane);
  wrap.appendChild(rightPane);
  wrap.appendChild(_renderHistoryCompareMinimap(data.density_buckets || []));
  _bindHistoryCompareRowPairHeightSync(wrap);
  return wrap;
}

function _historyCompareCountsSubtitle(totals = {}) {
  const total = Number(totals.left_total_lines || 0);
  const unchanged = Number(totals.equal_line_count || 0);
  const changed = Number(totals.changed_line_count || 0);
  const added = Number(totals.added_line_count || 0);
  const removed = Number(totals.removed_line_count || 0);
  return `${total.toLocaleString()} lines · ${unchanged.toLocaleString()} unchanged · `
    + `${changed.toLocaleString()} changed · ${added.toLocaleString()} added · `
    + `${removed.toLocaleString()} removed`;
}

function _renderHistoryCompareOmittedNote(truncated = {}) {
  const omitted = _historyCompareOmittedTotal(truncated);
  if (!omitted) return null;
  const note = document.createElement('div');
  note.className = 'history-compare-counts-note';
  note.textContent = `${omitted.toLocaleString()} changed line(s) or hunk(s) omitted by compare limits.`;
  return note;
}

function _historyCompareNoiseOmittedTotal(data = {}) {
  const left = Number(data.left?.output_source?.noise_lines_omitted || 0);
  const right = Number(data.right?.output_source?.noise_lines_omitted || 0);
  return Math.max(0, left) + Math.max(0, right);
}

function _renderHistoryCompareNoiseNote(data = {}) {
  const omitted = _historyCompareNoiseOmittedTotal(data);
  if (!omitted) return null;
  const note = document.createElement('div');
  note.className = 'history-compare-counts-note';
  note.textContent = `${omitted.toLocaleString()} noisy transcript line(s) folded out of this comparison.`;
  return note;
}

function _historyCompareObjectText(item, kind) {
  if (!item || typeof item !== 'object') return '';
  if (kind === 'artifact') {
    return item.workspace_path || item.display_name || item.id || '';
  }
  if (kind === 'entity') {
    return item.canonical_value || item.value || item.id || '';
  }
  return item.title || item.raw_line || item.id || '';
}

function _historyCompareObjectMeta(item, kind) {
  if (!item || typeof item !== 'object') return '';
  if (kind === 'artifact') {
    return [
      item.kind || 'file',
      item.byte_size !== undefined && item.byte_size !== null ? `${Number(item.byte_size).toLocaleString()} bytes` : '',
      item.detected_by || '',
    ].filter(Boolean).join(' · ');
  }
  if (kind === 'entity') {
    return [
      item.type || '',
      item.confidence || '',
      item.value && item.value !== item.canonical_value ? item.value : '',
    ].filter(Boolean).join(' · ');
  }
  return [
    item.severity || '',
    item.review_state || '',
    item.line_number !== undefined && item.line_number !== null ? `line ${item.line_number}` : '',
  ].filter(Boolean).join(' · ');
}

function _renderHistoryCompareObjectSection(title, items, kind, sign) {
  const safeItems = Array.isArray(items) ? items : [];
  const section = document.createElement('details');
  section.className = 'history-compare-lines history-compare-object-section';
  section.open = true;
  const summary = document.createElement('summary');
  summary.textContent = `${title} (${safeItems.length})`;
  section.appendChild(summary);
  if (!safeItems.length) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = `No ${title.toLowerCase()}.`;
    section.appendChild(empty);
    return section;
  }
  const list = document.createElement('div');
  list.className = 'history-compare-line-list';
  safeItems.forEach(item => {
    const compareLineIndex = _historyCompareNumber(item?.compare_line_index);
    const compareSide = sign === '+' ? 'b' : 'a';
    const row = compareLineIndex === null ? document.createElement('div') : document.createElement('button');
    if (row.tagName === 'BUTTON') {
      row.type = 'button';
      row.addEventListener('click', () => {
        _historyCompareScrollToLine(compareSide, compareLineIndex, { emit: true });
      });
      if (typeof bindPressable === 'function') bindPressable(row);
    }
    row.className = `history-compare-line history-compare-object-row${compareLineIndex === null ? '' : ' control-row'}`;
    row.dataset.objectKind = kind;
    row.dataset.compareSide = compareSide;
    if (compareLineIndex !== null) {
      row.dataset.compareLineIndex = String(compareLineIndex);
      row.classList.add('is-anchorable');
    }
    const mark = document.createElement('span');
    mark.className = sign === '+' ? 'history-compare-line-added' : 'history-compare-line-removed';
    mark.textContent = sign;
    row.appendChild(mark);
    const content = document.createElement('div');
    content.className = 'history-compare-object-content';
    const primary = document.createElement('code');
    primary.textContent = _historyCompareObjectText(item, kind);
    content.appendChild(primary);
    const meta = _historyCompareObjectMeta(item, kind);
    if (meta) {
      const metaEl = document.createElement('div');
      metaEl.className = 'history-compare-object-meta';
      metaEl.textContent = meta;
      content.appendChild(metaEl);
    }
    row.appendChild(content);
    list.appendChild(row);
  });
  section.appendChild(list);
  return section;
}

function _historyCompareHasTabCapacity(count) {
  const maxTabs = Number((typeof APP_CONFIG !== 'undefined' && APP_CONFIG && APP_CONFIG.max_tabs) || 0);
  if (!maxTabs || maxTabs <= 0 || typeof tabs === 'undefined' || !Array.isArray(tabs)) return true;
  return tabs.length + Number(count || 0) <= maxTabs;
}

function _restoreBothHistoryCompareRuns(left, right) {
  if (!left || !right) return Promise.reject(new Error('missing comparison runs'));
  if (!_historyCompareHasTabCapacity(2)) {
    showToast('Not enough tab capacity to restore both runs', 'error');
    return Promise.reject(new Error('not enough tab capacity'));
  }
  const leftTabId = createTab(`A: ${left.command || 'run'}`);
  if (!leftTabId) return Promise.reject(new Error('failed to create Run A tab'));
  const rightTabId = createTab(`B: ${right.command || 'run'}`);
  if (!rightTabId) return Promise.reject(new Error('failed to create Run B tab'));
  return Promise.all([
    restoreHistoryRunIntoTab(left, { targetTabId: leftTabId, hidePanelOnSuccess: false }),
    restoreHistoryRunIntoTab(right, { targetTabId: rightTabId, hidePanelOnSuccess: false }),
  ]).then(() => {
    if (typeof activateTab === 'function') activateTab(rightTabId, { focusComposer: false });
    return [leftTabId, rightTabId];
  });
}

function _renderHistoryComparison(data) {
  const overlay = _ensureHistoryCompareOverlay();
  const body = overlay.querySelector('#history-compare-body');
  const subtitle = overlay.querySelector('#history-compare-subtitle');
  if (!body) return;
  body.replaceChildren();
  if (!data._compareViewModeDefault) data._compareViewModeDefault = _historyCompareStoredViewMode();
  if (!data._compareContextDefault) data._compareContextDefault = _historyCompareStoredContext();
  const rawViewMode = _historyCompareCoerceViewMode(data._compareViewModeRaw || data._compareViewModeDefault);
  const viewMode = _historyCompareResolveViewMode(rawViewMode);
  const contextMode = _historyCompareCoerceContext(data._compareContext || data._compareContextDefault);
  data._compareViewModeRaw = rawViewMode;
  data._compareContext = contextMode;
  const totals = data.totals || {};
  const changedOutputCount = _historyCompareTotalChangedLines(totals);
  subtitle.textContent = viewMode === 'findings_only'
    ? 'Changed findings and artifacts'
    : (changedOutputCount ? _historyCompareCountsSubtitle(totals) : 'Changed findings and artifacts');

  const runs = document.createElement('div');
  runs.className = 'history-compare-run-grid';
  runs.appendChild(_historyCompareRunCard(data.left, 'Run A'));
  runs.appendChild(_historyCompareRunCard(data.right, 'Run B'));
  body.appendChild(runs);

  const deltas = data.deltas || {};
  const metrics = document.createElement('div');
  metrics.className = 'history-compare-metrics';
  if (deltas.exit_code) {
    metrics.appendChild(_compareMetricCell(
      'Exit',
      deltas.exit_code_changed ? `${deltas.exit_code.left} -> ${deltas.exit_code.right}` : `unchanged · ${deltas.exit_code?.right ?? 'n/a'}`,
      deltas.exit_code_changed ? 'is-changed' : '',
    ));
  }
  if (deltas.duration_seconds) {
    metrics.appendChild(_compareMetricCell('Duration', _compareFormatDelta(deltas.duration_seconds.delta || 0, 's')));
  }
  if (deltas.output_lines) {
    metrics.appendChild(_compareMetricCell('Lines', _compareFormatDelta(deltas.output_lines.delta || 0)));
  }
  if (deltas.findings) {
    metrics.appendChild(_compareMetricCell('Findings', _compareFormatDelta(deltas.findings.delta || 0)));
  }
  if (data.left && data.right && (
    Number.isFinite(Number(data.left.persisted_finding_count))
    || Number.isFinite(Number(data.right.persisted_finding_count))
  )) {
    metrics.appendChild(_compareMetricCell(
      'Stored findings',
      _compareFormatDelta(Number(data.right.persisted_finding_count || 0) - Number(data.left.persisted_finding_count || 0)),
    ));
  }
  if (data.left && data.right && (
    Number.isFinite(Number(data.left.artifact_count))
    || Number.isFinite(Number(data.right.artifact_count))
  )) {
    metrics.appendChild(_compareMetricCell(
      'Artifacts',
      _compareFormatDelta(Number(data.right.artifact_count || 0) - Number(data.left.artifact_count || 0)),
    ));
  }
  body.appendChild(metrics);
  const omittedNote = _renderHistoryCompareOmittedNote(data.truncated || {});
  if (omittedNote) body.appendChild(omittedNote);
  const noiseNote = _renderHistoryCompareNoiseNote(data);
  if (noiseNote) body.appendChild(noiseNote);

  const findingsTruncated = !!(
    data.truncated
    && data.truncated.findings
    && (data.truncated.findings.left || data.truncated.findings.right)
  );
  const artifactsTruncated = !!(
    data.truncated
    && data.truncated.artifacts
    && (data.truncated.artifacts.left || data.truncated.artifacts.right)
  );
  if (data.truncated && (
    data.truncated.left
    || data.truncated.right
    || data.truncated.changed_lines
    || findingsTruncated
    || artifactsTruncated
  )) {
    const note = document.createElement('div');
    note.className = 'history-compare-truncation';
    const limit = Number(data.truncated.item_limit || 0);
    note.textContent = findingsTruncated || artifactsTruncated
      ? `Comparison is partial because project findings or artifacts exceeded the per-run compare limit${limit ? ` of ${limit.toLocaleString()} items` : ''}.`
      : 'Comparison is partial because one or both outputs were truncated or the changed-line list hit its display limit.';
    body.appendChild(note);
  }

  const toolbar = document.createElement('div');
  toolbar.className = 'history-compare-toolbar';
  toolbar.appendChild(_renderHistoryCompareDisplayControls(data, viewMode));
  toolbar.appendChild(_renderHistoryCompareActionsMenu(data, deltas));
  toolbar.appendChild(_renderHistoryCompareNav(data));
  body.appendChild(toolbar);
  if (viewMode !== 'findings_only') {
    body.appendChild(_renderHistoryCompareSplitPane(data, {
      viewMode,
      contextLimit: _historyCompareContextLimit(contextMode),
    }));
  }

  const objects = data.objects || {};
  const findingObjects = objects.findings || {};
  const artifactObjects = objects.artifacts || {};
  const entityObjects = objects.entities || {};
  const addedFindings = Array.isArray(findingObjects.added) ? findingObjects.added : [];
  const removedFindings = Array.isArray(findingObjects.removed) ? findingObjects.removed : [];
  const addedArtifacts = Array.isArray(artifactObjects.added) ? artifactObjects.added : [];
  const removedArtifacts = Array.isArray(artifactObjects.removed) ? artifactObjects.removed : [];
  const addedEntities = Array.isArray(entityObjects.added) ? entityObjects.added : [];
  const removedEntities = Array.isArray(entityObjects.removed) ? entityObjects.removed : [];
  if (addedFindings.length) body.appendChild(_renderHistoryCompareObjectSection('Added findings', addedFindings, 'finding', '+'));
  if (removedFindings.length) body.appendChild(_renderHistoryCompareObjectSection('Removed findings', removedFindings, 'finding', '-'));
  if (addedEntities.length) body.appendChild(_renderHistoryCompareObjectSection('Added entities', addedEntities, 'entity', '+'));
  if (removedEntities.length) body.appendChild(_renderHistoryCompareObjectSection('Removed entities', removedEntities, 'entity', '-'));
  if (addedArtifacts.length) body.appendChild(_renderHistoryCompareObjectSection('Added artifacts', addedArtifacts, 'artifact', '+'));
  if (removedArtifacts.length) body.appendChild(_renderHistoryCompareObjectSection('Removed artifacts', removedArtifacts, 'artifact', '-'));
  if (
    !changedOutputCount
    && !addedFindings.length && !removedFindings.length
    && !addedEntities.length && !removedEntities.length
    && !addedArtifacts.length && !removedArtifacts.length
  ) {
    const empty = document.createElement('div');
    empty.className = 'history-compare-empty';
    empty.textContent = 'No changed output, findings, entities, or artifacts.';
    body.appendChild(empty);
  }
}

function fetchAndRenderHistoryComparison(leftId, rightId, options = {}) {
  if (!leftId || !rightId) return;
  _openHistoryCompareOverlay();
  const body = document.querySelector('#history-compare-body');
  if (body) {
    body.replaceChildren();
    const loading = document.createElement('div');
    loading.className = 'history-compare-empty';
    loading.textContent = 'Comparing runs...';
    body.appendChild(loading);
  }
  const url = options.url || `/history/compare?left=${encodeURIComponent(leftId)}&right=${encodeURIComponent(rightId)}`;
  apiFetch(url)
    .then(resp => resp.json().catch(() => ({})).then(data => {
      if (!resp.ok || data.error) {
        const err = new Error(data.error || `Compare request failed (${resp.status || 'unknown'})`);
        err.compareRequestError = true;
        throw err;
      }
      return data;
    }))
    .then(data => {
      _renderHistoryComparison(data);
    })
    .catch(err => {
      if (typeof console !== 'undefined' && typeof console.error === 'function') {
        console.error('[history compare] failed', err);
      }
      if (_historyCompareState && _historyCompareState.source) _renderHistoryCompareLauncher();
      const detail = err && err.compareRequestError && err.message ? `: ${err.message}` : '';
      showToast(`Failed to compare runs${detail}`, 'error');
    });
}
