function passageKey(thread) {
  if (thread.anchor_status !== 'attached') return null;
  const {path, anchor_kind: kind, start, end, render_anchor: anchor} = thread;
  if (kind === 'source') return JSON.stringify([path, kind, start, end]);
  if (kind === 'rendered' && anchor) return JSON.stringify([path, kind, anchor.quote, anchor.prefix, anchor.suffix]);
  if (kind === 'pdf' && anchor) return JSON.stringify([path, kind, anchor.version, anchor.page, anchor.rects]);
  return null;
}

function summarize(card) {
  const button = card.querySelector('.thread-summary');
  const body = card.querySelector('.message .comment-markdown');
  const words = body?.textContent.match(/^\s*(\S+(?:\s+\S+){0,4})/)?.[1].split(/\s+/);
  const excerpt = words?.slice(0, 4).join(' ') || (card.querySelector('[data-attachment]') ? 'Attachment' : 'Comment');
  const label = button.querySelector('.thread-excerpt');
  if (label.textContent !== excerpt) label.textContent = excerpt;
  button.querySelector('.thread-excerpt-end').hidden = !(words?.length > 4);
}

export function createThreadPreviews(list, surface, readSurface) {
  const sidebar = list.closest('.discussion-content');
  const filters = sidebar.querySelector('.thread-filters');
  const controls = new WeakMap();
  let rows = [], opened = null, path = null, align = false, group = false;
  let frame = 0, follow = false, dirty = false, scroller = null, aligned = false;

  function queueLayout() {
    if (!frame) frame = requestAnimationFrame(layout);
  }

  function schedule(scroll = false) {
    dirty = true;
    follow ||= scroll;
    queueLayout();
  }

  function rebuildStacks() {
    const stacks = [];
    for (const row of rows) {
      const {card, thread} = row;
      const compact = card.classList.contains('collapsed');
      const key = group && compact && thread ? passageKey(thread) : null;
      const previous = stacks.at(-1);
      if (key && previous?.key === key) previous.rows.push(row);
      else stacks.push({key, rows: [row]});
      if (compact) summarize(card);
    }
    const active = document.activeElement;
    for (const stack of stacks) {
      const {rows, key} = stack;
      const expanded = key === opened;
      const counted = rows.length > 2;
      const end = counted && !expanded ? 1 : rows.length - 1;
      rows.forEach(({card}, index) => {
        const type = rows.length === 1 ? '' : index > end ? 'overflow' : index === 0 ? 'first' : index === end ? 'last' : 'middle';
        if (type) card.dataset.previewStack = type;
        else delete card.dataset.previewStack;
        let button = controls.get(card);
        if (counted && index === 1) {
          if (!button) {
            button = document.createElement('button');
            button.type = 'button';
            button.className = 'thread-stack-toggle';
            button.setAttribute('data-thread-preview-control', '');
            card.append(button);
            controls.set(card, button);
          }
          button.textContent = expanded ? 'Show fewer' : '+' + (rows.length - 2) + ' more';
          button.setAttribute('aria-expanded', String(expanded));
          button.onclick = () => {
            opened = expanded ? null : key;
            rebuildStacks();
            schedule();
          };
        } else if (button) {
          if (active === button) card.querySelector('.thread-summary')?.focus({preventScroll: true});
          button.remove();
          controls.delete(card);
        }
        if (type === 'overflow' && card.contains(active)) {
          controls.get(rows[1].card)?.focus({preventScroll: true});
        }
      });
    }
    if (opened !== null && !stacks.some(stack => stack.key === opened && stack.rows.length > 2)) opened = null;
  }

  function setGap(card, gap) {
    const value = gap ? gap + 'px' : '';
    if (card.style.getPropertyValue('--thread-preview-gap') !== value) {
      if (value) card.style.setProperty('--thread-preview-gap', value);
      else card.style.removeProperty('--thread-preview-gap');
    }
  }

  function followReading(top) {
    const active = document.activeElement;
    if (!list.contains(active) || !active.matches('input,textarea,[contenteditable]')) sidebar.scrollTop = top;
  }

  function layout() {
    frame = 0;
    const track = follow, needsLayout = dirty;
    follow = dirty = false;
    if (list.getClientRects().length === 0) {
      aligned = false;
      scroller = null;
      sidebar.removeAttribute('data-aligned-thread-previews');
      list.style.removeProperty('min-height');
      for (const {card} of rows) setGap(card, 0);
      return;
    }
    if (track && !needsLayout && aligned && scroller) {
      followReading(scroller.scrollTop);
      return;
    }
    const compact = rows.filter(({card}) => card.classList.contains('collapsed') && card.dataset.previewStack !== 'overflow');
    const reading = align && compact.length ? readSurface(compact.map(({thread}) => thread)) : null;
    scroller = reading?.scroller || (align && compact.length ? surface.querySelector('.cm-scroller') || surface : null);
    const hasVisibleAnchor = reading && [...reading.points.values()].some(position => position >= reading.scrollTop &&
      position <= reading.scrollTop + reading.height);
    if (!reading?.points.size || (!aligned && !hasVisibleAnchor && !track)) {
      if (aligned) {
        sidebar.removeAttribute('data-aligned-thread-previews');
        list.style.removeProperty('min-height');
        for (const {card} of rows) setGap(card, 0);
      }
      aligned = false;
      return;
    }

    const fit = !aligned || track;
    aligned = true;
    sidebar.setAttribute('data-aligned-thread-previews', '');
    const sidebarTop = sidebar.getBoundingClientRect().top;
    const listOffset = list.getBoundingClientRect().top - sidebarTop + sidebar.scrollTop;
    const origin = reading.top - sidebarTop - listOffset;
    const before = list.clientTop;
    let end = before;
    // Read the natural row sizes once before positioning against passage geometry.
    const sizes = rows.map(({card}) => {
      const css = getComputedStyle(card);
      return {height: card.offsetHeight, after: parseFloat(css.marginBottom) || 0,
        previewHeight: card.querySelector('.thread-summary').offsetHeight};
    });
    rows.forEach(({card, thread}, index) => {
      const {height, after, previewHeight} = sizes[index];
      if (!height) return;
      const startsStack = !card.dataset.previewStack || card.dataset.previewStack === 'first';
      const point = card.classList.contains('collapsed') && startsStack ? reading.points.get(thread?.id) : undefined;
      const ideal = point === undefined ? end : point + origin - previewHeight / 2;
      const top = Math.max(end, ideal);
      setGap(card, Math.round(top - end));
      end = Math.round(top) + height + after;
    });
    const height = Math.max(0, reading.scrollHeight - reading.height + sidebar.clientHeight - listOffset);
    const minHeight = Math.ceil(height) + 'px';
    if (list.style.minHeight !== minHeight) list.style.minHeight = minHeight;
    // A reply being edited keeps its sidebar position.
    if (fit) followReading(reading.scrollTop);
  }

  document.addEventListener('scroll', event => {
    if (event.target !== scroller) return;
    follow = true;
    queueLayout();
  }, {capture: true, passive: true});
  const resize = new ResizeObserver(() => schedule());
  for (const element of [surface, sidebar, filters]) resize.observe(element);
  let observedContent = null;

  return {
    update(threads, nextPath, {align: positioned, group: stacked}) {
      if (path !== nextPath) {
        path = nextPath;
        opened = null;
        aligned = false;
        sidebar.removeAttribute('data-aligned-thread-previews');
        list.style.removeProperty('min-height');
        for (const {card} of rows) setGap(card, 0);
      }
      align = positioned;
      group = stacked;
      const byId = new Map(threads.map(thread => [thread.id, thread]));
      rows = [...list.querySelectorAll(':scope > .thread:not([hidden])')].map(card => ({card, thread: byId.get(Number(card.dataset.thread))}));
      rebuildStacks();
      const content = surface.querySelector('.markdown-preview, .pdf-reader');
      if (content !== observedContent) {
        if (observedContent) resize.unobserve(observedContent);
        if (content) resize.observe(content);
        observedContent = content;
      }
      schedule();
    },
    schedule
  };
}

export function threadMarkPositions(host, ids, origin) {
  const points = new Map();
  for (const mark of host.querySelectorAll('[data-anchor], [data-pdf-thread]')) {
    for (const id of (mark.dataset.anchors || mark.dataset.anchor || mark.dataset.pdfThread).split(',').map(Number)) {
      if (!ids.has(id) || points.has(id)) continue;
      const rect = mark.getClientRects()[0];
      if (rect?.height) points.set(id, (rect.top + rect.bottom) / 2 - origin);
    }
    if (points.size === ids.size) break;
  }
  return points;
}
