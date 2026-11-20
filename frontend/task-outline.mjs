import {iconButton} from './icons.mjs';
import {taskDragType, taskDropItem, taskDropPreview} from './task-drop-preview.mjs';

export const taskColumns = [['backlog', '◌', 'Backlog'], ['in_progress', '◐', 'In progress'],
  ['to_review', '◎', 'To review'], ['done', '✓', 'Done']];
const taskIndent = 16;
const taskStatus = new Map(taskColumns.map(([key, symbol, label], index) => {
  const [next, , nextLabel] = taskColumns[(index + 1) % taskColumns.length];
  return [key, {symbol, label, next, nextLabel}];
}));

export function cardTitle(card) {
  return card.milestone ? `M${card.milestone_number}: ${card.title}` : card.title;
}

// Keep ordering independent of the Kanban columns. Hidden ancestors are retained
// as context so an archived parent never makes an active descendant disappear.
export function outlineRows(cards, {rootId = null, archived = false, folded = new Set(),
  expanded = new Set(), collapsed = false, includeArchived = false} = {}) {
  const byId = new Map(cards.map(c => [c.id, c])), included = new Set();
  for (const card of cards) if (includeArchived || !!card.archived === archived) {
    let current = card;
    for (let i = 0; current && i < 32; i++, current = byId.get(current.parent_id)) included.add(current.id);
  }
  const children = new Map();
  for (const card of cards) {
    if (!included.has(card.id)) continue;
    const parent = byId.has(card.parent_id) ? card.parent_id : null;
    if (!children.has(parent)) children.set(parent, []);
    children.get(parent).push(card);
  }
  for (const siblings of children.values()) siblings.sort((a,b) =>
    (a.milestone && b.milestone ? a.milestone_number-b.milestone_number : Number(!!b.milestone)-Number(!!a.milestone)) ||
    a.outline_position-b.outline_position || a.id-b.id);
  const rows = [];
  function visit(parent, depth) {
    if (depth > 31) return;
    for (const card of children.get(parent) || []) {
      rows.push({card, depth, children: children.get(card.id)?.length || 0,
        context: !includeArchived && !!card.archived !== archived});
      if (collapsed ? expanded.has(card.id) : !folded.has(card.id)) visit(card.id, depth+1);
    }
  }
  visit(rootId, 0);
  return rows;
}

export function shiftTarget(cards, id, outdent = false) {
  const card = cards.find(c => c.id === id);
  if (!card || card.milestone || card.archived) return null;
  if (outdent) {
    const parent = cards.find(c => c.id === card.parent_id);
    if (!parent) return null;
    const siblings = cards.filter(c => c.parent_id === parent.parent_id && !c.archived)
      .sort((a,b) => a.outline_position-b.outline_position || a.id-b.id);
    return {parent_id:parent.parent_id, before:siblings[siblings.indexOf(parent)+1]?.id ?? null};
  }
  const siblings = cards.filter(c => c.parent_id === card.parent_id && !c.archived)
    .sort((a,b) => (a.milestone && b.milestone ? a.milestone_number-b.milestone_number : Number(!!b.milestone)-Number(!!a.milestone)) || a.outline_position-b.outline_position || a.id-b.id);
  const previous = siblings[siblings.indexOf(card)-1];
  return previous ? {parent_id:previous.id, before:null} : null;
}

export function milestoneInsertion(cards, id, after, exclude = null) {
  const anchor = cards.find(card => card.id === id);
  const milestone = anchor?.milestone ? anchor : cards.find(card => card.id === anchor?.milestone_id);
  if (!milestone) return null;
  return cards.filter(card => card.milestone && !card.archived && card.id !== exclude &&
    (after || !anchor.milestone ? card.milestone_number > milestone.milestone_number
      : card.milestone_number >= milestone.milestone_number))
    .sort((a, b) => a.milestone_number - b.milestone_number)[0]?.id ?? null;
}

const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};

export function mountTaskOutline(host, options) {
  const {getBoard, state, picked, write, open, contextMenu, changed, create, createMilestone, startDrag, getDrag, rootId = null,
    milestoneFilter, milestoneIds, clearFilter, hover} = options;
  const drafts = state.outlineDrafts ??= new Map(), views = state.outlineViews ??= new Map();
  const key = rootId ?? 'plan', view = views.get(key) ?? {collapsed: false, toggled: new Set()};
  views.set(key, view);
  const isExpanded = id => view.collapsed === view.toggled.has(id);
  let cursor = null;
  const section = element('section', undefined, 'task-outline'), list = element('div', undefined, 'task-outline-list'), status = element('div', undefined, 'task-outline-status');
  section.setAttribute('aria-label', rootId ? 'Card tasks' : 'Task hierarchy');
  list.setAttribute('role','list');
  list.style.setProperty('--task-indent', taskIndent + 'px');
  status.setAttribute('role','status');
  const add = element('button', '+ Add ' + (rootId ? 'subitem' : 'task'), 'task-outline-add');
  add.type='button';add.onclick=()=>create(rootId);
  const controls=element('div',undefined,'task-outline-controls');
  controls.setAttribute('role','group');controls.setAttribute('aria-label','Task list display');
  function setCollapsed(collapsed) {
    view.collapsed = collapsed;
    view.toggled.clear();
    render();
  }
  const collapse=iconButton('Collapse all tasks','collapse',()=>setCollapsed(true));
  const expand=iconButton('Expand all tasks','expand',()=>setCollapsed(false));
  if (clearFilter) controls.append(clearFilter);
  if (createMilestone) {
    controls.append(iconButton('Add milestone', 'addMilestone', () => {
      createMilestone(milestoneInsertion(getBoard().cards, cursor?.id, cursor?.after));
    }));
  }
  controls.append(collapse,expand);
  if(rootId){const heading=element('div',undefined,'task-outline-heading');heading.append(element('h3','Tasks'),controls);section.append(heading);}
  else (options.controlsHost||section).append(controls);
  section.append(list, add, status);host.append(section);
  const nodes = new Map();
  const preview = taskDropPreview(() => nodes.values());
  const draggedTitle = element('strong'), dropHint = element('span');
  preview.gap.append(draggedTitle, dropHint);
  const dragEvents = new AbortController();
  let rows = [], disposed = false, rendering = false, saving = Promise.resolve();
  let drop = null, savingDrop = false, moving = null;
  let controlRow = null;

  function updateDraggable(row) {
    row.draggable = row !== controlRow && row.dataset.archived !== 'true' &&
      !row.classList.contains('task-outline-editing');
  }
  function releaseControl() {
    const row = controlRow;
    controlRow = null;
    if (row) updateDraggable(row);
  }
  const pointerEvents = {capture: true, signal: dragEvents.signal};
  document.addEventListener('pointerup', releaseControl, pointerEvents);
  document.addEventListener('pointercancel', releaseControl, pointerEvents);
  window.addEventListener('blur', releaseControl, {signal: dragEvents.signal});

  function clearDrop(animate = true) {
    drop = null;
    preview.clear(animate);
  }
  function movingRows(source) {
    if (moving?.source === source) return moving;
    const cards = new Map(getBoard().cards.map(card => [card.id, card]));
    const ids = new Set(source.ids);
    function contains(id) {
      for (let card = cards.get(id); card; card = cards.get(card.parent_id)) {
        if (ids.has(card.id)) return true;
      }
      return false;
    }
    const origins = rows.filter(({card}) => contains(card.id)).map(({card}) => nodes.get(card.id));
    const height = origins.reduce((total, row) => total + row.offsetHeight, 0) + Math.max(0, origins.length - 1) * 2;
    moving = {source, contains, origins, height: height || 34};
    return moving;
  }
  function dropTarget(id, mode, source) {
    const cards = getBoard().cards;
    const card = cards.find(c => c.id === id);
    if (!card || card.archived || card.milestone || source.ids.includes(id)) return null;
    if (source.ids.some(id => cards.find(c => c.id === id)?.parent_id !== card.parent_id)) return null;
    const at = rows.findIndex(row => row.card.id === id);
    const next = rows.slice(at + 1).find(row => row.card.parent_id === card.parent_id && !source.ids.includes(row.card.id));
    return {parent_id: card.parent_id, before: mode === 'before' ? id : next?.card.id ?? null};
  }
  function milestoneDropTarget(id, mode, source) {
    if (movingRows(source).contains(id)) return null;
    const before = milestoneInsertion(getBoard().cards, id, mode === 'after', source.id);
    return {action: 'milestone_move', id: source.id, before};
  }
  function showDrop(target, source) {
    const {parent_id: parent = null, before} = target;
    const group = movingRows(source);
    const parentAt = rows.findIndex(r => r.card.id === parent);
    const depth = parent === rootId ? 0 : rows[parentAt]?.depth + 1;
    const beforeCard = getBoard().cards.find(card => card.id === before);
    const parentCard = getBoard().cards.find(card => card.id === parent);
    let hint = 'Move to end of list';
    if (beforeCard) hint = 'Insert before ' + cardTitle(beforeCard);
    else if (parentCard) hint = 'Move to end of ' + cardTitle(parentCard);
    else if (target.action === 'milestone_move') hint = 'Move to end of milestones';
    const dragged = getBoard().cards.find(card => card.id === source.id);
    draggedTitle.textContent = source.ids.length > 1 ? source.ids.length + ' selected cards' : cardTitle(dragged);
    dropHint.textContent = hint;
    preview.gap.title = hint;
    if (!Number.isFinite(depth) || (depth > 0 && !isExpanded(parent))) {
      preview.clear();
      return;
    }
    let anchor = nodes.get(before);
    if (target.action === 'milestone_move' && !anchor) {
      anchor = nodes.get(rows.find(r => r.depth === 0 && !r.card.milestone)?.card.id);
    } else if (depth > 0 && !anchor) {
      anchor = nodes.get(rows.slice(parentAt + 1).find(r => r.depth < depth && !group.contains(r.card.id))?.card.id);
    }
    preview.show(list, anchor || null, group.origins, group.height, depth * taskIndent);
  }
  list.ondragover = event => {
    if (!event.dataTransfer.types.includes(taskDragType) || savingDrop) return;
    const source = getDrag();
    if (!source) return;
    const hovered = taskDropItem(list, event.clientY, '.task-outline-row, .task-drop-preview');
    const overGap = hovered === preview.gap;
    const row = overGap ? drop?.row : hovered;
    if (!row) { clearDrop(); return; }
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = 'move';
    const id = Number(row.dataset.id);
    const localDrag = list.contains(source.element);
    const milestoneDrag = localDrag && source.element.classList.contains('task-outline-milestone');
    const midpoint = list.getBoundingClientRect().top + list.clientTop + row.offsetTop + row.offsetHeight / 2;
    const mode = overGap ? drop.mode : event.clientY > midpoint ? 'after' : 'before';
    const target = milestoneDrag ? milestoneDropTarget(id, mode, source) : dropTarget(id, mode, source);
    if (!target || movingRows(source).contains(target.parent_id) || movingRows(source).contains(target.before)) {
      clearDrop();
      return;
    }
    if (drop?.row === row && drop.mode === mode && drop.target.parent_id === target.parent_id &&
        drop.target.before === target.before) return;
    drop = {row, mode, target};
    showDrop(target, source);
  };
  list.ondragleave = event => {
    if (!savingDrop && !list.contains(event.relatedTarget)) clearDrop();
  };
  list.ondrop = async event => {
    if (!drop || savingDrop) return;
    event.preventDefault();
    event.stopPropagation();
    const source = getDrag();
    if (!source) { clearDrop(); return; }
    const {target} = drop;
    savingDrop = true;
    await mutate(target.action ? target : {action: 'outline_move', ids: source.ids, ...target});
    savingDrop = false;
    clearDrop();
  };
  document.addEventListener('dragend', () => {
    if (!savingDrop) clearDrop();
    moving = null;
  }, {signal: dragEvents.signal});

  async function mutate(data, revision) {
    await saving;
    if (disposed) return false;
    const result = await write(data,revision);
    if (!result) status.textContent = options.error();
    else status.textContent='';
    return result;
  }
  async function saveName(id) {
    const operation=async()=>{
      if (disposed) return false;
      const draft=drafts.get(id), card=getBoard().cards.find(c=>c.id===id);
      if (!draft || !card || draft.value===card.title) { drafts.delete(id); return true; }
      const {value, revision} = draft;
      const result=await write({action:'update',ids:[id],changes:{title:value}},revision);
      if(result) {
        if(drafts.get(id)?.value===value) drafts.delete(id);
        else if(drafts.get(id)?.revision===revision && getBoard().revision===revision+1) {
          drafts.get(id).revision=revision+1;
        }
        if (!disposed) { status.replaceChildren();render(); }
      } else if (!disposed) {
        status.textContent=options.error();
        const latest=getBoard().cards.find(c=>c.id===id);
        if(latest && revision!==getBoard().revision) {
          status.append(element('span', ` Saved title: ${latest.title}. `));
          const retry=element('button','Keep my title using this revision');retry.type='button';
          const reviewed=getBoard().revision;
          retry.onclick=()=>{if(drafts.has(id)){drafts.get(id).revision=reviewed;saveName(id);}};
          status.append(retry);
        }
      }
      return result;
    };
    saving=saving.then(operation,operation);
    return saving;
  }
  function focusRow(id) { nodes.get(id)?.querySelector('.task-outline-name')?.focus({preventScroll:true}); }
  async function openCard(id) {
    await saving;
    const card=getBoard().cards.find(c=>c.id===id);
    if(!disposed && card)open(card);
  }
  async function shift(id, outdent, editing = false) {
    if(!await saveName(id))return;
    const target=shiftTarget(getBoard().cards,id,outdent);
    if (!target) return;
    const index = rows.findIndex(row => row.card.id === id);
    if (await mutate({action:'outline_move', ids:[id], ...target})) {
      if (!outdent && !isExpanded(target.parent_id)) {
        if (view.collapsed) view.toggled.add(target.parent_id);
        else view.toggled.delete(target.parent_id);
        render();
      }
      if (nodes.has(id)) {
        if (editing) focusRow(id);
        else nodes.get(id).focus();
      } else if (rows.length) {
        selectRow(rows[Math.min(index, rows.length - 1)].card.id);
      } else {
        picked.clear();
        changed();
        add.focus();
      }
    }
  }
  function nextFocus(id, direction) {
    const index=rows.findIndex(r=>r.card.id===id);
    focusRow(rows[index+direction]?.card.id);
  }
  function selectRow(id) {
    picked.clear();
    picked.add(id);
    changed();
    nodes.get(id)?.focus();
  }
  function makeRow(id) {
    const row=element('div',undefined,'task-outline-row');row.dataset.id=id;row.setAttribute('role','listitem');row.tabIndex=-1;
    const fold = iconButton('', 'triangle', () => {
      if (view.toggled.has(id)) view.toggled.delete(id);
      else view.toggled.add(id);
      render();
    });
    fold.classList.add('task-outline-fold');
    const symbol = element('button', undefined, 'task-outline-symbol');
    symbol.type = 'button';
    let cycling = false;
    symbol.onclick = async () => {
      if (cycling) return;
      cycling = true;
      try {
        await saving;
        const card = getBoard().cards.find(card => card.id === id);
        if (!symbol.disabled && card) {
          await mutate({action: 'update', ids: [id], changes: {status: taskStatus.get(card.status).next}});
        }
      } finally {
        cycling = false;
      }
    };
    const check = element('input', undefined, 'task-outline-check');
    check.type = 'checkbox';
    check.onchange = async () => {
      const status = check.checked ? 'done' : 'backlog';
      check.disabled = true;
      if (!await mutate({action: 'update', ids: [id], changes: {status}})) {
        check.checked = getBoard().cards.find(card => card.id === id)?.status === 'done';
        check.disabled = row.dataset.archived === 'true' || row.classList.contains('task-outline-context');
      }
    };
    const reference=element('button',undefined,'task-outline-reference');reference.type='button';
    reference.onclick = () => {
      if (milestoneFilter && row.classList.contains('task-outline-milestone')) milestoneFilter(id);
      else openCard(id);
    };
    if (hover) {
      row.onpointerenter = () => hover(id);
      row.onpointerleave = () => hover(null);
    }
    const prefix = element('button', undefined, 'task-outline-prefix');
    prefix.type = 'button';
    prefix.onclick = () => openCard(id);
    const name = element('input', undefined, 'task-outline-name');
    const title = element('span', undefined, 'task-outline-title');
    title.append(name);
    name.type='text';name.maxLength=500;name.draggable=false;
    name.oninput = () => {
      title.dataset.value = name.value;
      const previous = drafts.get(id);
      drafts.set(id, {value: name.value, revision: previous?.revision ?? getBoard().revision});
    };
    name.onfocus=()=>{
      if (name.readOnly) return;
      row.classList.add('task-outline-editing');
      updateDraggable(row);
    };
    name.onblur=()=>{
      row.classList.remove('task-outline-editing');
      updateDraggable(row);
      if(!rendering)saveName(id);
    };
    name.onkeydown=async event=>{
      if(event.key==='Tab') {
        if(!name.readOnly && shiftTarget(getBoard().cards,id,event.shiftKey)) {
          event.preventDefault();await shift(id,event.shiftKey,true);
        }
        return;
      }
      if (name.readOnly || event.isComposing) return;
      if(event.key==='Escape') {event.preventDefault();event.stopPropagation();drafts.delete(id);status.replaceChildren();render();name.blur();return;}
      if(event.key==='Enter') {
        event.preventDefault();
        if(!await saveName(id))return;
        if(event.ctrlKey||event.metaKey)create(id);
        else if(event.shiftKey)create(getBoard().cards.find(c=>c.id===id)?.parent_id??null);
        else nextFocus(id,1);
      }
      if(['ArrowUp','ArrowDown'].includes(event.key)) {
        event.preventDefault();const direction=event.key==='ArrowUp'?-1:1;
        if(!await saveName(id))return;
        if(event.altKey && row.dataset.archived !== 'true') {
          const card=getBoard().cards.find(c=>c.id===id);
          const siblings=rows.map(r=>r.card).filter(c=>c.parent_id===card.parent_id &&
            !!c.milestone===!!card.milestone && (!card.milestone || !c.archived));
          const at=siblings.findIndex(c=>c.id===id), target=direction<0?siblings[at-1]:siblings[at+2];
          if (direction>0 ? at<siblings.length-1 : at>0) {
            const before = target?.id ?? null;
            await mutate(card.milestone ? {action:'milestone_move',id,before}
              : {action:'outline_move',ids:[id],parent_id:card.parent_id,before});
          }
          focusRow(id);
        } else nextFocus(id,direction);
      }
    };
    const progress = element('span', undefined, 'task-outline-progress');
    const pen = iconButton('Open card details', 'pen', () => openCard(id));
    pen.classList.add('task-outline-pen');
    row.append(fold, check, reference, prefix, title, symbol, progress, pen);
    if (createMilestone) {
      row.onpointermove = event => {
        const bounds = row.getBoundingClientRect();
        cursor = {id, after: event.clientY >= bounds.top + bounds.height / 2};
      };
      row.onfocusin = () => { cursor = {id, after: true}; };
    }
    row.addEventListener('click',event=>{
      if(event.ctrlKey||event.metaKey) {event.preventDefault();event.stopPropagation();picked.has(id)?picked.delete(id):picked.add(id);changed();}
    },true);
    row.onclick = event => {
      if (event.target.closest('button,input')) return;
      selectRow(id);
    };
    row.onkeydown = event => {
      if (event.target !== row || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === 'Escape' && picked.has(id)) {
        picked.clear();
        changed();
      } else if (event.key === 'Tab' && picked.has(id)) {
        shift(id, event.shiftKey);
      } else if (event.key === 'Enter') {
        openCard(id);
      } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        const at = rows.findIndex(item => item.card.id === id);
        selectRow(rows[at + (event.key === 'ArrowDown' ? 1 : -1)]?.card.id ?? id);
      } else return;
      event.preventDefault();
      event.stopPropagation();
    };
    row.ondblclick = event => {
      if (event.target.closest('button,input') || name.readOnly) return;
      name.focus({preventScroll: true});
    };
    row.oncontextmenu=event=>contextMenu(event,id);
    row.onpointerdown = event => {
      releaseControl();
      if (event.button !== 0 || !event.target.closest('button,input')) return;
      // Native dragging would otherwise pick up the ancestor row from a control.
      controlRow = row;
      updateDraggable(row);
    };
    row.ondragstart=event=>{
      if (event.target !== row || !row.draggable) { event.preventDefault(); return; }
      startDrag(event,id,row.classList.contains('task-outline-milestone') ? [id] : undefined);
    };
    return row;
  }
  function render() {
    if(disposed)return;
    const dropPositions = savingDrop && drop ? preview.capture() : null;
    clearDrop(false);
    moving = null;
    rendering=true;
    const focused=section.contains(document.activeElement)?document.activeElement:null;
    const selection=focused?.matches('input[type=text]')?[focused.selectionStart,focused.selectionEnd]:null;
    const cards = getBoard().cards;
    const scope = {rootId, archived: !!state.archived, includeArchived: rootId === null};
    rows = outlineRows(cards, {...scope, collapsed: view.collapsed,
      [view.collapsed ? 'expanded' : 'folded']: view.toggled});
    const allRows = view.collapsed || view.toggled.size ? outlineRows(cards, scope) : rows;
    collapse.disabled = !rows.some(({card, children}) => children && isExpanded(card.id));
    expand.disabled = !allRows.some(({card, children}) => children && !isExpanded(card.id));
    collapse.setAttribute('aria-pressed', String(view.collapsed && !view.toggled.size));
    expand.setAttribute('aria-pressed', String(!view.collapsed && !view.toggled.size));
    const totals = new Map();
    if (rootId === null) for (const card of cards) {
      if (card.archived || !card.milestone_id) continue;
      const count = totals.get(card.milestone_id) ?? {done: 0, total: 0};
      count.total++;
      if (card.status === 'done') count.done++;
      totals.set(card.milestone_id, count);
    }
    const visible=new Set(rows.map(r=>r.card.id));
    for (const [id, row] of nodes) if (!visible.has(id)) {
      if (row.matches(':hover')) hover?.(null);
      row.remove();
      nodes.delete(id);
    }
    for(let index=0;index<rows.length;index++) {
      const {card,depth,children,context}=rows[index];
      let row=nodes.get(card.id);if(!row){row=makeRow(card.id);nodes.set(card.id,row);}
      row.style.setProperty('--task-depth',depth);row.dataset.depth=depth;
      row.classList.toggle('task-outline-milestone',!!card.milestone);row.classList.toggle('task-outline-done',card.status==='done');row.classList.toggle('task-outline-context',context);
      row.dataset.archived = !!card.archived;
      row.setAttribute('aria-selected',String(picked.has(card.id)));
      row.tabIndex = picked.has(card.id) || (!picked.size && index === 0) ? 0 : -1;
      updateDraggable(row);
      const [fold, check, reference, prefix, title, symbol, progress] = row.children;
      const name = title.firstElementChild;
      const expanded = isExpanded(card.id);
      if (children) row.setAttribute('aria-expanded', String(expanded)); else row.removeAttribute('aria-expanded');
      const foldAction = (expanded ? 'Collapse ' : 'Expand ') + card.title;
      fold.disabled = !children;
      fold.title = foldAction;
      fold.setAttribute('aria-label', foldAction);
      fold.setAttribute('aria-expanded', String(expanded));
      const itemStatus = taskStatus.get(card.status);
      symbol.textContent = itemStatus.symbol;
      symbol.title = `${itemStatus.label} → ${itemStatus.nextLabel}`;
      symbol.setAttribute('aria-label', 'Cycle status for ' + card.title);
      symbol.setAttribute('aria-description', `Current status: ${itemStatus.label}. Next status: ${itemStatus.nextLabel}.`);
      symbol.disabled = context || !!card.archived;
      check.checked = card.status === 'done';
      check.disabled = context || !!card.archived;
      check.setAttribute('aria-label', 'Complete ' + card.title);
      check.setAttribute('aria-description', itemStatus.label);
      const filterable = milestoneFilter && card.milestone;
      reference.textContent = card.milestone ? '◇' : '#C' + String(card.id).padStart(2, '0');
      reference.title = (filterable ? 'Filter board by ' : 'Open ') + cardTitle(card);
      reference.setAttribute('aria-label', (filterable ? 'Filter board by ' : 'Open ') +
        (card.milestone ? '#M' + card.milestone_number : reference.textContent));
      if (filterable) reference.setAttribute('aria-pressed', String(milestoneIds.has(card.id)));
      else reference.removeAttribute('aria-pressed');
      prefix.textContent = card.milestone ? 'M' + card.milestone_number + ':' : '';
      prefix.hidden = !card.milestone;
      if (card.milestone) {
        prefix.title = 'Open ' + cardTitle(card);
        prefix.setAttribute('aria-label', 'Open #M' + card.milestone_number + ': ' + card.title);
      }
      if(!drafts.has(card.id))name.value=card.title;
      else if(document.activeElement!==name)name.value=drafts.get(card.id).value;
      if (title.dataset.value !== name.value) title.dataset.value = name.value;
      name.readOnly=context;name.setAttribute('aria-label','Task name '+card.id);name.title=cardTitle(card);
      const total = totals.get(card.id);
      progress.textContent = card.milestone && total ? `${total.done}/${total.total}` : '';
      progress.title = total ? `${total.done} of ${total.total} tasks done` : '';
      if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);
    }
    for(const id of drafts.keys())if(!getBoard().cards.some(c=>c.id===id))drafts.delete(id);
    if(focused?.isConnected&&document.activeElement!==focused){focused.focus({preventScroll:true});if(selection)focused.setSelectionRange(...selection);}
    preview.settle(dropPositions);
    rendering=false;
  }
  render();
  return {render,dispose(){disposed=true;dragEvents.abort();clearDrop(false);controls.remove();section.remove();},focus:focusRow};
}
