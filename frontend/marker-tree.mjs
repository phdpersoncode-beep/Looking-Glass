import {icon,iconButton} from './icons.mjs';

const TAGS = ['P0','P1','P2','P3','TODO','NOTE'];
const make = (tag, className, text) => {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

function groups(parent, file, markers) {
  const parts = file.path.split('/');
  for (const name of parts.slice(0, -1)) {
    if (!parent.folders.has(name)) parent.folders.set(name, branch(name, 'folder', parent));
    parent.count += markers.length;
    parent = parent.folders.get(name);
  }
  const leaf = branch(parts.at(-1), 'file', parent);
  leaf.file = file;
  leaf.markers = markers;
  leaf.count = markers.length;
  parent.files.push(leaf);
  parent.count += markers.length;
}

function branch(name, kind, parent) {
  return {name, kind, key: (parent?.key ?? '') + '/' + name, folders: new Map(), files: [], count: 0};
}

function groupMatches(files, byTag, query, tag) {
  const root = branch('', 'root');
  const tags = new Map();
  for (const file of files) {
    const pathMatch = file.path.toLowerCase().includes(query);
    const matches = !tag && pathMatch ? file.markers : file.markers.filter(
      marker => (!tag || marker.kind === tag) &&
        (pathMatch || (marker.kind + ' ' + marker.text).toLowerCase().includes(query))
    );
    if (!matches.length) continue;
    if (!byTag) {
      groups(root, file, matches);
      continue;
    }
    const byKind = new Map();
    for (const marker of matches) {
      if (!byKind.has(marker.kind)) byKind.set(marker.kind, []);
      byKind.get(marker.kind).push(marker);
    }
    for (const [kind, markers] of byKind) {
      if (!tags.has(kind)) tags.set(kind, branch(kind, 'tag', root));
      groups(tags.get(kind), file, markers);
    }
  }
  return byTag ? TAGS.flatMap(tag => tags.has(tag) ? [tags.get(tag)] : []) : [...root.folders.values(), ...root.files];
}

function markerLocation(marker) {
  return marker.cell ? `Cell ${marker.cell}, line ${marker.line}` : `Line ${marker.line}`;
}

// A changed draft can still reveal an unchanged marker line if it has a
// unique surviving location. Never select a different occurrence by guess.
export function markerOffset(doc, marker, saved) {
  if (!saved) return doc.line(marker.line).from + marker.column;
  const text = saved.line(marker.line).text;
  const lines = doc.iterLines();
  let line = 0, found = 0;
  while (!lines.next().done) {
    line++;
    if (lines.value !== text) continue;
    if (found) return null;
    found = line;
  }
  return found ? doc.line(found).from + marker.column : null;
}

export function mountMarkerTree({root, read, open}) {
  const $ = id => document.getElementById(id);
  const toggle = $('marker-section-toggle'), panel = $('marker-section-content');
  const fileToggle = $('file-section-toggle');
  const results = $('marker-results'), status = $('marker-status');
  const count = $('marker-count'), filter = $('marker-filter');
  const panels = $('file-explorers');
  const storageKey = 'looking-glass-marker-tree:' + root;
  let snapshot, etag, loading = false, pending = false, error = '';
  let byTag = false, filterTimer, query = '', tag = '';
  const browse = {expanded: false, overrides: new Map()};
  const filtered = {expanded: true, overrides: new Map()};
  const isFiltered = () => Boolean(query || tag);
  const expansion = () => isFiltered() ? filtered : browse;

  const actions = $('marker-actions');
  const search = iconButton('Filter markers', 'filter', () => {
    filter.hidden = !filter.hidden;
    search.setAttribute('aria-pressed', String(!filter.hidden));
    if (filter.hidden) {
      filter.value = '';
      applyFilter();
    } else filter.focus();
  });
  search.setAttribute('aria-pressed', 'false');
  search.setAttribute('aria-controls', filter.id);
  const group = iconButton('Group markers by tag', 'tag', () => {
    byTag = !byTag;
    group.setAttribute('aria-pressed', String(byTag));
    render();
  });
  group.setAttribute('aria-pressed', 'false');
  function setExpanded(expanded) {
    const state = expansion();
    state.expanded = expanded;
    state.overrides.clear();
    render();
  }
  const collapse = iconButton('Collapse all marker branches', 'collapse', () => setExpanded(false));
  const expand = iconButton('Expand all marker branches', 'expand', () => setExpanded(true));
  const reload = iconButton('Refresh markers', 'refresh', () => refresh(true));
  const tagFilter = make('select', 'marker-tag-filter');
  tagFilter.setAttribute('aria-label', 'Filter markers by tag');
  for (const kind of ['', ...TAGS]) {
    const option = make('option', '', kind || 'All tags');
    option.value = kind;
    tagFilter.append(option);
  }
  tagFilter.onchange = applyFilter;
  actions.append(search, group, collapse, expand, reload, tagFilter);

  function applyFilter() {
    clearTimeout(filterTimer);
    const next = filter.value.trim().toLowerCase();
    if (next === query && tagFilter.value === tag) return;
    query = next;
    tag = tagFilter.value;
    filtered.expanded = true;
    filtered.overrides.clear();
    render();
  }

  filter.oninput = () => {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(applyFilter, 100);
  };
  filter.onkeydown = event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      search.click();
      search.focus();
    }
  };

  function renderHit(file, marker, prefix) {
    const button = make('button', 'marker-hit');
    button.type = 'button';
    button.dataset.markerKey = prefix + ':' + (marker.cell ?? 0) + ':' + marker.line + ':' + marker.column;
    const tag = make('span', 'marker-tag', marker.kind);
    tag.dataset.kind = marker.kind;
    const location = markerLocation(marker);
    button.title = [marker.kind, marker.text].filter(Boolean).join(' ') + '\n' + file.path + ' · ' + location;
    button.append(tag, make('span', 'marker-label', marker.text || location));
    button.onclick = () => open(file.path, file.version, marker);
    return button;
  }

  function renderBranch(node, depth) {
    const item = make('details', 'marker-branch');
    const key = (byTag ? 'tag:' : 'path:') + node.key;
    const summary = make('summary', 'marker-branch-row');
    summary.dataset.markerKey = key;
    summary.title = node.file?.path ?? node.name;
    summary.style.setProperty('--marker-depth', depth);
    const label = make('span', node.kind === 'tag' ? 'marker-tag' : 'marker-label', node.name);
    if (node.kind === 'tag') label.dataset.kind = node.name;
    else {
      const extension = node.name.split('.').at(-1).toLowerCase();
      const type = node.kind === 'folder' ? 'folder' :
        extension === 'ipynb' ? 'notebookFile' :
        ['md', 'markdown'].includes(extension) ? 'markdownFile' : 'codeFile';
      const symbol = icon(type);
      symbol.classList.add('marker-node-icon');
      symbol.dataset.icon = type;
      summary.append(symbol);
    }
    summary.append(label, make('span', 'explorer-count', node.count));
    const children = make('div', 'marker-children');
    item.append(summary, children);
    const {expanded, overrides} = expansion();
    item.open = overrides.get(key) ?? expanded;
    function showChildren() {
      if (node.file) {
        children.style.setProperty('--marker-depth', depth + 1);
        children.replaceChildren(...node.markers.map(marker => renderHit(node.file, marker, key)));
      } else {
        const nested = [...node.folders.values(), ...node.files];
        children.replaceChildren(...nested.map(child => renderBranch(child, depth + 1)));
      }
    }
    if (item.open) showChildren();
    // Synchronous user gestures keep branch state consistent across refreshes.
    summary.onclick = event => {
      event.preventDefault();
      item.open = !item.open;
      overrides.set(key, item.open);
      if (item.open) showChildren();
      else children.replaceChildren();
    };
    return item;
  }

  function render() {
    if (panel.hidden) return;
    const nodes = snapshot ? groupMatches(snapshot.files, byTag, query, tag) : [];
    const focusKey = document.activeElement?.dataset.markerKey;
    const top = results.scrollTop;
    results.replaceChildren(...nodes.map(node => renderBranch(node, 0)));
    if (top) results.scrollTop = top;
    if (focusKey) {
      const focused = results.querySelector('[data-marker-key="' + CSS.escape(focusKey) + '"]');
      (focused ?? toggle).focus({preventScroll: true});
    }
    renderStatus(nodes.length);
  }

  function renderStatus(nodes = results.children.length) {
    const messages = [];
    if (error) messages.push(error);
    else if (!snapshot) messages.push('Scanning workspace…');
    else if (!nodes) messages.push(isFiltered() ? 'No matching markers.' : 'No markers found.');
    if (snapshot?.truncated) messages.push('Marker results are limited.');
    status.textContent = messages.join(' ');
    status.hidden = !messages.length;
    count.textContent = snapshot ? String(snapshot.count) : '';
    count.hidden = !snapshot?.count;
    collapse.disabled = expand.disabled = !nodes;
  }

  function visible() {
    return !panel.hidden && !panels.hidden && !document.hidden &&
      !document.documentElement.classList.contains('zen-mode');
  }

  async function refresh(force = false) {
    if (!visible()) return;
    if (loading) {
      pending ||= force;
      return;
    }
    loading = true;
    if (!snapshot && !error) renderStatus();
    try {
      const response = await read(etag);
      error = '';
      etag = response.etag;
      if (response.data) {
        snapshot = response.data;
        render();
      } else if (!panel.hidden) renderStatus();
    } catch {
      error = 'Could not refresh markers.';
      if (!panel.hidden) renderStatus();
    } finally {
      loading = false;
      if (pending) {
        pending = false;
        refresh();
      }
    }
  }

  function setOpen(value) {
    panel.hidden = !value;
    toggle.setAttribute('aria-expanded', String(value));
    if (value) {
      render();
      queueMicrotask(() => refresh());
    } else {
      results.replaceChildren();
    }
  }

  toggle.onclick = () => {
    localStorage.setItem(storageKey, String(panel.hidden));
    setOpen(panel.hidden);
  };
  fileToggle.onclick = () => {
    const content = $('file-section-content');
    const value = content.hidden;
    content.hidden = !value;
    $('file-actions').hidden = !value;
    fileToggle.setAttribute('aria-expanded', String(value));
  };
  document.addEventListener('visibilitychange', () => refresh());
  setOpen(localStorage.getItem(storageKey) === 'true');
  return {refresh};
}
