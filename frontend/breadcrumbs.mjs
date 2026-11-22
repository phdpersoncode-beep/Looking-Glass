import {icon} from './icons.mjs';

const MAX_ROWS = 200;
const parentOf = path => path.slice(0, Math.max(0, path.lastIndexOf('/')));

export function mountBreadcrumbs(host, picker, {read, open}) {
  const up = picker.querySelector('[data-breadcrumb-up]');
  const location = picker.querySelector('[data-breadcrumb-location]');
  const query = picker.querySelector('input');
  const list = picker.querySelector('[role=listbox]');
  const status = picker.querySelector('[role=status]');
  let anchor, currentPath, currentLabel, directory, entries = [], matches = [];
  let selected = -1, first = 0, revision = 0, truncated = false, loading = false, error = '';

  const visible = () => picker.matches(':popover-open');

  function place() {
    if (!visible() || !anchor) return;
    const bounds = anchor.getBoundingClientRect();
    const width = Math.min(360, innerWidth - 16);
    const left = Math.min(Math.max(8, bounds.left), innerWidth - width - 8);
    const top = bounds.bottom + 5;
    Object.assign(picker.style, {
      left: left + 'px', top: top + 'px', width: width + 'px',
      maxHeight: Math.max(0, Math.min(430, innerHeight - top - 8)) + 'px',
    });
  }

  function close(focus = false) {
    revision++;
    const from = anchor;
    anchor = null;
    if (visible()) picker.hidePopover();
    from?.setAttribute('aria-expanded', 'false');
    if (focus && from?.isConnected) from.focus({preventScroll: true});
  }

  function renderStatus() {
    let text = '';
    if (loading) text = 'Loading files…';
    else if (error) text = error;
    else if (!matches.length) text = query.value ? 'No matching files or folders.' : 'This folder is empty.';
    else if (matches.length > MAX_ROWS) text = 'Type to narrow the list.';
    if (truncated) text += (text ? ' ' : '') + 'This folder exceeds the file limit.';
    status.textContent = text;
    status.hidden = !text;
  }

  function selectRow() {
    const row = list.querySelector('[data-index="' + selected + '"]');
    for (const old of list.querySelectorAll('[aria-selected=true]')) old.setAttribute('aria-selected', 'false');
    if (row) {
      row.setAttribute('aria-selected', 'true');
      query.setAttribute('aria-activedescendant', row.id);
      row.scrollIntoView({block: 'nearest'});
    } else query.removeAttribute('aria-activedescendant');
  }

  function showRows() {
    if (selected < first) first = Math.max(0, selected);
    if (selected >= first + MAX_ROWS) first = selected - MAX_ROWS + 1;
    const fragment = document.createDocumentFragment();
    matches.slice(first, first + MAX_ROWS).forEach((entry, index) => {
      const row = document.createElement('button');
      const at = first + index;
      row.type = 'button';
      row.id = 'breadcrumb-option-' + at;
      row.dataset.index = at;
      row.tabIndex = -1;
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', 'false');
      row.setAttribute('aria-posinset', String(at + 1));
      row.setAttribute('aria-setsize', String(matches.length));
      if (entry.path === currentPath) row.setAttribute('aria-current', 'page');
      const name = document.createElement('span');
      name.textContent = entry.name;
      row.title = entry.path;
      row.append(icon(entry.directory ? 'folder' : 'codeFile'), name);
      if (entry.directory) {
        const arrow = document.createElement('span');
        arrow.className = 'breadcrumb-next';
        arrow.setAttribute('aria-hidden', 'true');
        row.append(arrow);
      }
      row.onclick = () => choose(entry);
      fragment.append(row);
    });
    list.replaceChildren(fragment);
    selectRow();
    renderStatus();
  }

  function filter(preferred) {
    const needle = query.value.trim().toLowerCase();
    matches = needle ? entries.filter(entry => entry.name.toLowerCase().includes(needle)) : entries;
    selected = matches.findIndex(entry => entry.path === preferred);
    if (selected < 0 && matches.length) selected = 0;
    first = 0;
    list.scrollTop = 0;
    showRows();
  }

  async function show(path, preferred) {
    const request = ++revision;
    directory = path;
    entries = [];
    truncated = false;
    error = '';
    loading = true;
    up.disabled = !directory;
    location.textContent = directory || 'Workspace';
    location.title = directory;
    query.value = '';
    filter();
    query.focus({preventScroll: true});
    try {
      const result = await read(directory);
      if (request !== revision || !visible()) return;
      entries = result.entries;
      truncated = result.truncated;
      loading = false;
      filter(preferred);
    } catch (failure) {
      if (request !== revision || !visible()) return;
      error = failure.message;
      loading = false;
      renderStatus();
    }
  }

  function choose(entry) {
    if (!entry) return;
    if (entry.directory) show(entry.path);
    else {
      close(true);
      open(entry.path);
    }
  }

  function toggle(crumb, path) {
    if (anchor === crumb && visible()) {
      close(true);
      return;
    }
    anchor?.setAttribute('aria-expanded', 'false');
    anchor = crumb;
    anchor.setAttribute('aria-expanded', 'true');
    if (!visible()) picker.showPopover();
    place();
    show(parentOf(path), path);
  }

  up.onclick = () => {if (directory) show(parentOf(directory), directory);};
  query.oninput = () => filter();
  query.onkeydown = event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      choose(matches[selected]);
    } else if (['ArrowDown', 'ArrowUp'].includes(event.key) && matches.length) {
      event.preventDefault();
      const delta = event.key === 'ArrowDown' ? 1 : -1;
      selected = Math.min(matches.length - 1, Math.max(0, selected + delta));
      if (selected < first || selected >= first + MAX_ROWS) showRows();
      else selectRow();
    }
  };
  picker.onkeydown = event => {
    if (event.key !== 'Escape') return;
    event.preventDefault();
    event.stopPropagation();
    close(true);
  };
  function dismiss(event) {
    if (visible() && !picker.contains(event.target) && !host.contains(event.target)) close();
  }
  document.addEventListener('pointerdown', dismiss);
  document.addEventListener('focusin', dismiss);
  window.addEventListener('resize', place);
  host.addEventListener('scroll', place);

  return {
    update(path, label) {
      if (path === currentPath && label === currentLabel) return;
      close();
      currentPath = path;
      currentLabel = label;
      host.classList.toggle('has-breadcrumbs', Boolean(path));
      if (!path) {
        host.textContent = label;
        return;
      }
      host.replaceChildren();
      let target = '';
      for (const part of path.split('/')) {
        if (target) {
          const divider = document.createElement('span');
          divider.className = 'breadcrumb-divider';
          divider.textContent = '/';
          divider.setAttribute('aria-hidden', 'true');
          host.append(divider);
        }
        target = target ? target + '/' + part : part;
        const prefix = target;
        const crumb = document.createElement('button');
        crumb.type = 'button';
        crumb.className = 'document-crumb';
        crumb.textContent = part;
        crumb.title = prefix;
        crumb.setAttribute('aria-label', 'Browse neighboring files from ' + prefix);
        crumb.setAttribute('aria-haspopup', 'dialog');
        crumb.setAttribute('aria-controls', picker.id);
        crumb.setAttribute('aria-expanded', 'false');
        crumb.onclick = () => toggle(crumb, prefix);
        host.append(crumb);
      }
      host.scrollLeft = host.scrollWidth;
    }
  };
}
