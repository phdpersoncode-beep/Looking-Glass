import {mountTaskActivity} from './task-activity.mjs';
import {cardTitle, mountTaskOutline, taskColumns as columns} from './task-outline.mjs';
import {bindTaskDismiss} from './task-dialog.mjs';
import {iconButton} from './icons.mjs';
import {fileReferences} from './file-references.mjs';
import {taskDragType, taskDropItem, taskDropPreview} from './task-drop-preview.mjs';
export function cardReference(id) { return `#C${String(id).padStart(2, "0")}`; }
export function displayReference(card) { return card.reference || cardReference(card.id); }
function fuzzyCard(card, query) {
  query = query.trim();
  if (!query) return true;
  if (/^#?m\d+$/i.test(query)) return !!card.milestone && Number((card.milestone_reference || card.reference || "").replace(/^#m/i,"")) === Number(query.replace(/^#?m/i,""));
  if (/^#?c\d+$/i.test(query)) return Number(query.replace(/^#?c/i,"")) === card.id;
  let at = 0;
  const text = (card.title + " " + card.description).toLocaleLowerCase();
  for (const char of query.toLocaleLowerCase()) {
    at = text.indexOf(char, at);
    if (at < 0) return false;
    at++;
  }
  return true;
}
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== void 0) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function button(text, action, title = text) {
  const b = el("button", text);
  b.type = "button";
  b.title = title;
  b.setAttribute("aria-label", title);
  b.onclick = action;
  return b;
}
function mountTasks(host, state, api, options = {}) {
  let board = { cards: [], revision: 0 }, disposed = false, busy = false, refreshing = null, editor = null, outline = null, context = null;
  let dragSource = null, laneDrop = null, savingDrop = false;
  const drafts = state.drafts ??= new Map();
  const resume = state.documentReturn;
  const picked = new Set(), root = el("section", void 0, "task-board"), tools = el("div", void 0, "task-tools"), search = el("input"), archived = el("input"), bulk = el("div", void 0, "task-bulk"), lanes = el("div", void 0, "task-lanes"), notice = el("p", void 0, "task-notice");
  const filterWrap = el('div', undefined, 'task-filter');
  const filter = button('', () => toggleFilter(filterMenu.hidden), 'Filter by milestone');
  const filterLabel = el('span');
  const filterMenu = el('div', undefined, 'task-filter-menu');
  filterMenu.id = 'task-milestone-filter-' + crypto.randomUUID();
  filterMenu.setAttribute('role', 'group');
  filterMenu.setAttribute('aria-label', 'Milestone filters');
  filter.setAttribute('aria-controls', filterMenu.id);
  filter.append(el('span', '◇'), filterLabel);
  filter.firstChild.setAttribute('aria-hidden', 'true');
  filterWrap.append(filter, filterMenu);
  toggleFilter(false);
  filterWrap.onkeydown = event => {
    if (event.key !== 'Escape' || filterMenu.hidden) return;
    event.preventDefault();
    event.stopPropagation();
    toggleFilter(false);
    filter.focus();
  };
  function toggleFilter(open) {
    filterMenu.hidden = !open;
    filter.setAttribute('aria-expanded', String(open));
  }
  function renderMilestoneFilter() {
    const choices = board.cards.filter(card => card.milestone).sort((a, b) => a.milestone_number - b.milestone_number);
    const selected = choices.find(card => card.id === Number(state.filter));
    if (!selected) state.filter = '';
    const label = selected ? cardTitle(selected) : 'Milestones';
    filterLabel.textContent = label;
    filter.title = selected ? label : 'Filter by milestone';
    filter.classList.toggle('active', !!selected);
    filter.disabled = !choices.length;
    if (!choices.length) toggleFilter(false);
    const focused = filterMenu.contains(document.activeElement) ? document.activeElement.dataset.milestone : undefined;
    const makeChoice = (id, text) => {
      const item = button(text, () => {
        state.filter = selected?.id === id || id === 0 ? '' : String(id);
        toggleFilter(false);
        render();
        filter.focus();
      }, text);
      item.dataset.milestone = id;
      item.setAttribute('aria-pressed', String((selected?.id ?? 0) === id));
      return item;
    };
    filterMenu.replaceChildren(makeChoice(0, 'All milestones'), ...choices.map(card =>
      makeChoice(card.id, cardTitle(card) + (card.archived ? ' (archived)' : ''))));
    if (focused !== undefined) filterMenu.querySelector(`[data-milestone="${focused}"]`)?.focus({preventScroll: true});
  }
  const lanePreview = taskDropPreview(() => lanes.querySelectorAll('.task-card'));
  function startDrag(event, id, ids = picked.has(id) ? [...picked] : [id]) {
    const data = {id, ids, x: event.clientX};
    event.dataTransfer.setData('text/plain', String(id));
    event.dataTransfer.setData(taskDragType, JSON.stringify(data));
    event.dataTransfer.effectAllowed = 'move';
    const boardCard = lanes.querySelector(`.task-card[data-id="${id}"]`);
    dragSource = {...data, element: event.currentTarget, cardHeight: boardCard?.offsetHeight || 65};
    dragSource.element.classList.add('task-drag-source');
    document.body.classList.add('task-drag-active');
  }
  function endDrag() {
    dragSource?.element.classList.remove('task-drag-source');
    dragSource = null;
    document.body.classList.remove('task-drag-active');
  }
  function clearLaneDrop(animate = true) {
    laneDrop = null;
    lanePreview.clear(animate);
  }
  search.placeholder = "Search cards\u2026";
  search.setAttribute("aria-label", "Search cards");
  search.value = state.query || "";
  archived.type = "checkbox";
  archived.checked = !!state.archived;
  const archiveLabel = el("label", "Show archive ");
  archiveLabel.append(archived);
  notice.setAttribute("role", "status");
  tools.append(search, filterWrap, archiveLabel, button("+ Task", () => editNew("backlog"), "Create task"));
  const muted = el("input");
  muted.type = "checkbox";
  muted.checked = !!state.muted;
  const muteLabel = el("label", "Mute ");
  muteLabel.append(muted);
  muted.onchange = () => {
    state.muted = muted.checked;
    localStorage.setItem("looking-glass-task-muted", String(muted.checked));
  };
  if (state.muted === void 0) muted.checked = localStorage.getItem("looking-glass-task-muted") === "true";
  tools.append(muteLabel);
  root.append(tools, bulk, notice, lanes);
  host.append(root);
  options.onSidebarMode?.(true);
  if(options.sidebar){
    const heading=el('div',undefined,'panel-heading'), label=el('span','TASKS'), count=el('span','0');
    label.append(' ',count);heading.append(label);
    const help=el('p','Click to open · Double-click to rename','task-outline-help');
    help.title='Enter saves; Shift+Enter adds a sibling; Ctrl/Cmd+Enter adds a subitem. Tab / Shift+Tab nest; Alt+Up/Down reorders. Drag vertically to reorder and right/left to nest or outdent. Ctrl/Cmd+click selects; right-click opens actions.';
    options.sidebar.append(heading,help);
    outline=mountTaskOutline(options.sidebar,outlineOptions({controlsHost:heading,
      createMilestone: before => editNew('backlog', null, {milestone: true, before})}));
    outline.updateCount=()=>count.textContent=String(board.cards.length);
  }
  function outlineOptions(extra={}){
    return {getBoard:()=>board,state,picked,write:change,open:card=>{if(card)edit(card);},contextMenu:openContext,changed:render,create:parent=>editNew('backlog',parent),error:()=>notice.textContent,startDrag,getDrag:()=>dragSource,...extra};
  }
  function closeContext(){context?.remove();context=null;}
  function openContext(event,id){
    event.preventDefault();event.stopPropagation();closeContext();
    if(!picked.has(id)){picked.clear();picked.add(id);render();}
    context=el('div',undefined,'task-context-menu');context.setAttribute('role','menu');context.setAttribute('aria-label','Selected task actions');
    const action=(label,fn)=>{const b=button(label,()=>{closeContext();fn();});b.setAttribute('role','menuitem');context.append(b);};
    const ids=[...picked];
    for(const card of board.cards.filter(c=>c.milestone&&!c.archived&&!ids.includes(c.id)).sort((a,b)=>a.milestone_number-b.milestone_number))action('Assign to '+cardTitle(card),()=>change({action:'update',ids,changes:{milestone_id:card.id}}));
    action('No milestone',()=>change({action:'update',ids,changes:{milestone_id:null}}));
    action('Archive',()=>change({action:'update',ids,changes:{archived:true}}));
    action('Restore',()=>change({action:'update',ids,changes:{archived:false}}));
    action('Delete',()=>confirmDelete(ids));
    action('Clear selection',()=>{picked.clear();render();});
    (document.querySelector('.task-detail[open]')||document.body).append(context);
    const bounds = context.getBoundingClientRect();
    context.style.left=Math.max(4,Math.min(event.clientX,innerWidth-bounds.width-4))+'px';
    context.style.top=Math.max(4,Math.min(event.clientY,innerHeight-bounds.height-4))+'px';
    context.onkeydown=e=>{
      const buttons=[...context.querySelectorAll('button')],at=buttons.indexOf(document.activeElement);
      if(e.key==='Escape'){e.preventDefault();closeContext();}
      else if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();buttons[(at+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length].focus();}
    };
    context.firstChild?.focus({preventScroll:true});
  }
  const contextAbort=new AbortController();
  document.addEventListener('pointerdown', event => {
    if (context && !context.contains(event.target)) closeContext();
    if (!filterWrap.contains(event.target)) toggleFilter(false);
  }, {signal: contextAbort.signal});
  document.addEventListener('dragend', () => {
    endDrag();
    if (!savingDrop) clearLaneDrop();
  }, {signal: contextAbort.signal});
  lanes.ondragleave = event => {
    if (!savingDrop && !lanes.contains(event.relatedTarget)) clearLaneDrop();
  };
  function fail(error) {
    if (!disposed) notice.textContent = error.message;
  }
  function milestones(select, value = "", exclude = []) {
    select.replaceChildren(el("option", "No milestone"));
    select.firstChild.value = "";
    for (const card of board.cards.filter((c) => c.milestone && (!c.archived || c.id === Number(value)) && !exclude.includes(c.id)).sort((a,b)=>a.milestone_number-b.milestone_number)) {
      const option = el("option", "\u25C7 " + displayReference(card) + " " + card.title + (card.archived ? " (archived)" : ""));
      option.value = card.id;
      select.append(option);
    }
    select.value = value;
  }
  function celebrate() {
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const burst = el("div", void 0, "task-confetti");
      for (let i = 0; i < 18; i++) {
        const bit = el("i");
        bit.style.setProperty("--x", `${(Math.random() - 0.5) * 260}px`);
        bit.style.setProperty("--y", `${30 + Math.random() * 100}px`);
        bit.style.setProperty("--r", `${Math.random() * 360}deg`);
        burst.append(bit);
      }
      const popup=document.querySelector('.task-detail[open]');
      if(popup){const rect=popup.getBoundingClientRect();burst.style.position='fixed';burst.style.left=(rect.left+rect.width*.75)+'px';burst.style.top=(rect.top+Math.min(rect.height/2,140))+'px';}
      (popup||root).append(burst);
      setTimeout(() => burst.remove(), 950);
    }
    if (!muted.checked) {
      try {
        const Audio = window.AudioContext || window.webkitAudioContext;
        const audio = new Audio(), osc = audio.createOscillator(), gain = audio.createGain();
        osc.connect(gain);
        gain.connect(audio.destination);
        osc.frequency.setValueAtTime(880, audio.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1320, audio.currentTime + 0.12);
        gain.gain.setValueAtTime(0.035, audio.currentTime);
        gain.gain.exponentialRampToValueAtTime(1e-4, audio.currentTime + 0.5);
        osc.start();
        osc.stop(audio.currentTime + 0.5);
        osc.onended = () => audio.close();
        audio.resume().catch(() => {
        });
      } catch {
      }
    }
  }
  async function change(data, revision = board.revision) {
    if (busy) {
      notice.textContent = "Another task change is saving. Try again in a moment.";
      return false;
    }
    busy = true;
    notice.textContent = "";
    try {
      const old = board;
      const next = await api("tasks", "POST", { ...data, revision, author:options.author?.() || "User" });
      if (disposed) return false;
      document.querySelectorAll('.task-detail[open]').forEach(d=>d.acknowledge?.(old.revision,next.revision,data));
      if (next.revision > board.revision || !lanes.children.length) {
        board = next;
        render();
      }
      const incomplete = new Set(old.cards.filter(c => c.status !== 'done').map(c => c.id));
      if (next.cards.some(c => !c.milestone && c.status === 'done' && incomplete.has(c.id))) celebrate();
      return true;
    } catch (error) {
      fail(error);
      if (error.status === 409) {
        await refreshing;
        await refresh(true);
      }
      return false;
    } finally {
      busy = false;
    }
  }
  // Unchanged polls do not touch the DOM or read card payloads.
  function refresh(duringDrag = false) {
    if (disposed || refreshing || (dragSource && !duringDrag)) return refreshing;
    refreshing = (async () => {
      try {
        const next = await api("tasks" + (lanes.children.length ? "?revision=" + board.revision : ""));
        if (!disposed && (!dragSource || duringDrag) && next && (next.revision > board.revision || !lanes.children.length)) {
          board = next;
          render();
          if (resume && state.documentReturn === resume) {
            const card = board.cards.find(c => c.id === resume.id);
            delete state.documentReturn;
            if (card) edit(card);
            else notice.textContent = "The card was deleted while you were viewing the file.";
          }
        }
      } catch (error) {
        fail(error);
      } finally {
        refreshing = null;
      }
    })();
    return refreshing;
  }
  function render() {
    const dropPositions = savingDrop && laneDrop ? lanePreview.capture() : null;
    clearLaneDrop(false);
    const scroll = lanes.scrollLeft, focused = document.activeElement, focusedCard = focused?.closest(".task-card"), focusedId = focusedCard?.dataset.id, focusedAction = focusedCard && focused !== focusedCard ? focused.getAttribute("aria-label") : null, assignment = bulk.querySelector("select")?.value || "", bulkFocused = bulk.contains(focused) ? focused?.getAttribute("aria-label") : null;
    renderMilestoneFilter();
    const byId = new Map(board.cards.map(card => [card.id, card]));
    for (const id of picked) if (!byId.has(id)) picked.delete(id);
    for (const id of drafts.keys()) if (!byId.has(id)) drafts.delete(id);
    bulk.replaceChildren();
    if (picked.size) {
      bulk.append(el("span", `${picked.size} selected`));
      const assign = el("select");
      milestones(assign, assignment);
      assign.setAttribute("aria-label", "Assign selected cards to milestone");
      bulk.append(assign, button("Assign", () => change({ action: "update", ids: [...picked], changes: { milestone_id: Number(assign.value) || null } })), button("Archive", () => change({ action: "update", ids: [...picked], changes: { archived: true } })), button("Restore", () => change({ action: "update", ids: [...picked], changes: { archived: false } })), button("Delete", () => confirmDelete([...picked])), button("Clear", () => {
        picked.clear();
        render();
      }));
    }
    lanes.replaceChildren();
    const milestoneId = Number(state.filter), query = search.value.trim();
    const milestoneQuery = /^#?m\d+$/i.test(query);
    for (const [status, symbol, label] of columns) {
      const lane = el("section", void 0, "task-lane");
      lane.dataset.status = status;
      lane.setAttribute("aria-label", label);
      const cards = board.cards.filter(c => !c.milestone && c.status === status && !!c.archived === archived.checked &&
        (!milestoneId || c.milestone_id === milestoneId) &&
        (!query || fuzzyCard(milestoneQuery ? (byId.get(c.milestone_id) ?? c) : c, query)));
      const heading = el("header");
      heading.append(el("h3", symbol + " " + label), el("span", String(cards.length)), button("+", () => editNew(status), "Add task to " + label));
      if (status === 'done' && !archived.checked) {
        const archiveAll = iconButton('Archive all done tasks', 'archive', () =>
          change({action: 'archive_done', ids: cards.map(card => card.id)}));
        archiveAll.classList.add('task-archive-done');
        archiveAll.disabled = !cards.length;
        heading.append(archiveAll);
      }
      lane.append(heading);
      lane.ondragover = (e) => {
        if (!e.dataTransfer.types.includes(taskDragType) || savingDrop) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (!dragSource) return;
        const hovered = taskDropItem(lane, e.clientY, '.task-card, .task-drop-preview');
        if (hovered === lanePreview.gap) return;
        const source = lanes.querySelector(`.task-card[data-id="${dragSource.id}"]`);
        if (hovered && hovered === source) {
          clearLaneDrop();
          return;
        }
        laneDrop = {lane, before: hovered ? Number(hovered.dataset.id) : null};
        lanePreview.show(lane, hovered || lane.querySelector('.task-empty'), source ? [source] : [], dragSource.cardHeight);
      };
      lane.ondrop = async (e) => {
        if (!e.dataTransfer.types.includes(taskDragType) || savingDrop) return;
        e.preventDefault();
        let id;
        try { ({id} = JSON.parse(e.dataTransfer.getData(taskDragType))); } catch { return; }
        const hovered = dragSource ? taskDropItem(lane, e.clientY, '.task-card') : e.target.closest('.task-card');
        const before = laneDrop?.lane === lane ? laneDrop.before : hovered ? Number(hovered.dataset.id) : null;
        if (!Number.isSafeInteger(id) || id === before) return;
        savingDrop = true;
        await change({action: 'move', id, status, before});
        savingDrop = false;
        clearLaneDrop();
      };
      for (const card of cards) {
        const item = el("article", void 0, "task-card");
        item.dataset.id = card.id;
        item.tabIndex = 0;
        item.setAttribute("aria-label", card.title);
        item.setAttribute("aria-selected", String(picked.has(card.id)));
        item.draggable = !card.archived;
        item.ondragstart = (e) => startDrag(e, card.id);
        const title = el("div", cardTitle(card), "task-card-title");
        item.append(title);
        const reference=el("span", displayReference(card), "task-reference");
        reference.title="Permanent card ID: " + cardReference(card.id);
        item.append(reference);
        if (card.milestone_id) {
          const parent = byId.get(card.milestone_id);
          if (parent) { const assignment=el("small", "\u25C7 " + displayReference(parent) + " " + parent.title, "task-assignment"); assignment.title="Milestone: " + parent.title; item.append(assignment); }
        }
        item.onclick = (e) => {
          if (e.target.closest("button")) return;
          if (e.ctrlKey || e.metaKey) {
            picked.has(card.id) ? picked.delete(card.id) : picked.add(card.id);
            render();
          } else edit(card);
        };
        item.oncontextmenu=e=>openContext(e,card.id);
        item.onkeydown = (e) => {
          if (e.target !== item) return;
          if (e.key === "Enter") {
            e.preventDefault();
            edit(card);
          }
          if (e.key === " ") {
            e.preventDefault();
            picked.has(card.id) ? picked.delete(card.id) : picked.add(card.id);
            render();
          }
        };
        const promote = button("\u25C7", () => change({action: "update", ids: [card.id], changes: {milestone: true}}), "Promote to milestone");
        promote.className = "task-promote";
        item.append(promote);
        lane.append(item);
      }
      if (!cards.length) lane.append(el("p", "No cards", "task-empty"));
      lanes.append(lane);
    }
    document.querySelectorAll(".task-dialog").forEach(d=>{
      if(d.cardId&&!byId.has(d.cardId)){d.close();d.remove();}
      else {d.refreshReference?.();d.refreshActivity?.();}
    });
    outline?.render();outline?.updateCount();
    lanes.scrollLeft = scroll;
    lanePreview.settle(dropPositions);
    if (focusedId) {
      const card = lanes.querySelector('[data-id="' + focusedId + '"]');
      (focusedAction ? [...card?.querySelectorAll("button") || []].find((b) => b.getAttribute("aria-label") === focusedAction) : card)?.focus({ preventScroll: true });
    } else if (bulkFocused) {
      [...bulk.querySelectorAll("button,select")].find((b) => b.getAttribute("aria-label") === bulkFocused)?.focus({ preventScroll: true });
    }
  }
  function dialog(title, detail=false) {
    const previousFocus=document.activeElement, openerId=previousFocus?.closest('.task-card')?.dataset.id;
    const previous=document.querySelector('.task-detail[open]');
    if(detail&&previous){previous.retainDraft?.();previous.close();previous.remove();}
    const d = el("dialog", void 0, "task-dialog"), heading = el("h2", title);
    if(detail)d.classList.add('task-detail');
    heading.id = 'task-heading-' + crypto.randomUUID();
    d.setAttribute('aria-labelledby', heading.id);
    d.append(heading);
    document.body.append(d);
    editor = d;
    d.addEventListener("close", () => {
      d.remove();
      notice.textContent = "";
      if (editor === d) editor = document.querySelector('.task-detail[open]');
      if(detail&&!document.querySelector('dialog[open]')){
        const target=previousFocus?.isConnected?previousFocus:openerId?lanes.querySelector('[data-id="'+openerId+'"]'):null;
        target?.focus({preventScroll:true});
      }
    });
    if(detail){
      bindTaskDismiss(d,()=>{d.retainDraft?.();d.close();});
    }
    return d;
  }
  function field(form, text, node) {
    const wrap = el("div", void 0, "task-field"), label = el("label", text);
    node.id = "task-field-" + crypto.randomUUID();
    label.htmlFor = node.id;
    wrap.append(label, node);
    form.append(wrap);
    return node;
  }
  function editNew(status, parentId = null, {milestone = false, before = null} = {}) {
    const d = dialog(milestone ? 'New milestone' : 'New task'), form = el("form"), title = field(form, "Title", el("input"));
    title.name = "title";
    title.required = true;
    title.maxLength = 500;
    form.append(button("Cancel", () => d.close()));
    const save = el("button", "Create");
    save.type = "submit";
    form.append(save);
    form.onsubmit = async (e) => {
      e.preventDefault();
      save.disabled = true;
      const placement = milestone ? {milestone, before} : {parent_id: parentId};
      if (await change({action: "create", title: title.value, status, ...placement})) d.close();
      else {
        save.disabled = false;
        error.textContent = notice.textContent;
      }
    };
    const error = el("p");
    error.setAttribute("role", "alert");
    form.append(error);
    d.append(form);
    d.showModal();
    title.focus();
  }
  function edit(card) {
    if(editor?.open&&editor.cardId===card.id){editor.querySelector('[aria-label=Title]')?.focus();return;}
    const draft = drafts.get(card.id);
    const original = draft?.original ?? {
      title: card.title, description: card.description, status: card.status, milestone_id: card.milestone_id
    };
    let revision = draft?.revision ?? board.revision;
    const d = dialog(cardTitle(card),true), form = el("form"), title = el("textarea",undefined,'task-detail-title'), metadata=el('div',undefined,'task-detail-metadata'), status = field(metadata, "Status", el("select")), parent = field(metadata, "Milestone", el("select")), description = field(form, "Description", el("textarea"));
    form.prepend(metadata);
    status.parentElement.classList.add('task-status-field');parent.parentElement.classList.add('task-milestone-field');
    status.title='Status';parent.title='Milestone';
    d.cardId=card.id;
    const actions=el('div',undefined,'task-detail-actions'), content=el('div',undefined,'task-detail-content');
    const close=iconButton('Close card','close',()=>{retainDraft();d.close();});
    actions.setAttribute('role','toolbar');actions.setAttribute('aria-label','Card actions');close.classList.add('task-detail-close');
    const heading=d.querySelector('h2'), prefix=el('span',undefined,'task-detail-prefix');
    content.append(heading);
    d.append(actions,content);
    heading.className='task-detail-heading';
    heading.replaceChildren(prefix,title);
    form.id='task-edit-'+crypto.randomUUID();title.setAttribute('form',form.id);
    title.setAttribute('aria-label','Title');title.title='Edit card title';title.rows=1;
    title.name='title';
    title.value = draft?.title ?? card.title;
    title.required = true;
    title.maxLength = 500;
    const sizeTitle=()=>{title.style.height='0px';title.style.height=title.scrollHeight+'px';};
    title.onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();title.blur();}};
    description.value = draft?.description ?? card.description;
    description.maxLength = 100000;
    description.dataset.taskFileMentions = '';
    const related = el('div',undefined,'task-related-files');
    const fileLinks = el('div',undefined,'task-file-links');
    const hint = el('p','Type @ to link a workspace file.','task-file-hint');
    hint.id = description.id + '-hint';
    description.setAttribute('aria-describedby',hint.id);
    related.append(el('h3','Related files'),fileLinks);
    form.append(hint,related);
    let linkedPaths = [];
    const refreshRelatedFiles = () => {
      const paths = [...new Set(fileReferences(description.value).map(ref => ref.path))].filter(path => !path.includes('//'));
      if (paths.length === linkedPaths.length && paths.every((path,index) => path === linkedPaths[index])) return;
      linkedPaths = paths;
      related.hidden = !paths.length;
      fileLinks.replaceChildren(...paths.map(path => {
        const link = el('a',path);
        link.href = '#file-' + encodeURIComponent(path);
        link.dataset.fileReference = path;
        link.title = 'Open ' + path;
        return link;
      }));
    };
    related.hidden = true;
    refreshRelatedFiles();
    for (const [value, symbol, label] of columns) {
      const o = el("option", symbol+' '+label);
      o.value = value;
      status.append(o);
    }
    status.value = draft?.status ?? card.status;
    milestones(parent, (draft ? draft.milestone_id : card.milestone_id) || "", [card.id]);
    parent.firstChild.textContent='◇ No milestone';
    parent.disabled = !!card.milestone;
    const permanent=el("p", "Card " + cardReference(card.id), "task-permanent-reference");
    d.querySelector("h2").after(permanent);
    d.refreshReference=()=>{
      const latest=board.cards.find(c=>c.id===card.id);
      if(latest){
        prefix.textContent=latest.milestone?'M'+latest.milestone_number+':':'';
        prefix.hidden=!latest.milestone;
        heading.setAttribute('aria-label',latest.milestone?'M'+latest.milestone_number+': '+title.value:title.value);
        permanent.title="This card ID is retained when the milestone is demoted.";
      }
      for(const option of parent.options){
        const milestone=board.cards.find(c=>c.id===Number(option.value));
        if(milestone)option.textContent="◇ " + displayReference(milestone) + " " + milestone.title + (milestone.archived?" (archived)":"");
      }
    };
    d.refreshReference();
    const save=iconButton('Save','save');save.classList.add('task-save');
    save.type = "submit";save.setAttribute('form',form.id);
    const readFields = () => ({
      title:title.value, description:description.value, status:status.value, milestone_id:Number(parent.value)||null
    });
    const editedFields = fields => Object.fromEntries(Object.entries(fields).filter(([key,value]) => value !== original[key]));
    const retainDraft = () => {
      const fields = readFields();
      if (Object.keys(editedFields(fields)).length) drafts.set(card.id, {revision, original, ...fields});
      else drafts.delete(card.id);
    };
    title.oninput=()=>{retainDraft();d.refreshReference();sizeTitle();};
    d.retainDraft=retainDraft;
    d.acknowledge=(before,after,data)=>{
      // Local edits elsewhere in the outline can advance this draft's base;
      // edits to the same fields still require conflict review.
      const editsThisCard=data.action==='update'&&data.ids.includes(card.id);
      if(revision===before && after===before+1 && !editsThisCard && data.action!=='delete'){
        revision=after;if(drafts.has(card.id))retainDraft();
      }
    };
    form.oninput = form.onchange = retainDraft;
    const cancel=iconButton('Cancel','undo',()=>{drafts.delete(card.id);d.close();});cancel.title='Discard edits (Cancel)';
    actions.append(save, cancel, iconButton(card.milestone ? "Convert to task" : "Promote to milestone", 'milestone',async () => {
      if (await change({ action: "update", ids: [card.id], changes: { milestone: !card.milestone } }, revision)) d.close();
      else error.textContent = notice.textContent;
    }), iconButton(card.archived ? "Restore" : "Archive", card.archived?'restore':'archive',async () => {
      if (await change({ action: "update", ids: [card.id], changes: { archived: !card.archived } }, revision)) d.close();
      else error.textContent = notice.textContent;
    }), iconButton("Delete", 'trash',() => confirmDelete([card.id], d)),close);
    const error = el("p");
    error.setAttribute("role", "alert");
    form.append(error);
    description.addEventListener('input',refreshRelatedFiles);
    d.addEventListener('click', async event => {
      const link = event.target.closest('a[data-file-reference]');
      if (!link) return;
      event.preventDefault();
      event.stopPropagation();
      retainDraft();
      try {
        await options.openDocument(link.dataset.fileReference,card.id);
      } catch (problem) {
        error.textContent = problem.message;
        error.scrollIntoView({block:'nearest'});
      }
    });
    form.onsubmit = async (e) => {
      e.preventDefault();
      const changes = editedFields(readFields());
      if (!Object.keys(changes).length) { drafts.delete(card.id); d.close(); return; }
      save.disabled = true;
      if (await change({ action: "update", ids: [card.id], changes }, revision)) { drafts.delete(card.id); d.close(); }
      else {
        save.disabled = false;
        error.textContent = notice.textContent;
        // Keep unsent fields intact until the user reviews the saved version.
        if (board.revision !== revision) {
          const latest = board.cards.find((c) => c.id === card.id), reviewedRevision = board.revision;
          if (latest) {
            const details = el("details"), summary = el("summary", "Review latest saved card");
            details.append(summary, el("pre", JSON.stringify({ title: latest.title, description: latest.description, status: latest.status, milestone_id: latest.milestone_id, milestone: !!latest.milestone, milestone_number:latest.milestone_number, archived: !!latest.archived }, null, 2)), button("Use this revision and keep my edits", () => {
              revision = reviewedRevision;
              retainDraft();
              error.textContent = "Latest revision acknowledged. Review your fields, then save.";
            }));
            error.append(details);
          }
        }
      }
    };
    content.append(form);
    const checklistHost=el('div',undefined,'task-checklist');content.append(checklistHost);
    const checklist=mountTaskOutline(checklistHost,outlineOptions({rootId:card.id,write:async(data,base)=>{
      const before=board.revision,saved=await change(data,base??revision);
      if(saved&&revision===before&&board.revision===before+1){revision=board.revision;if(drafts.has(card.id))retainDraft();}
      return saved;
    }}));
    const refreshReference=d.refreshReference;
    d.refreshReference=()=>{refreshReference();checklist.render();};
    d.addEventListener('close',checklist.dispose);
    const activity = mountTaskActivity(content, card.id, {
      api, state, getRevision:()=>board.revision,
      write:async data=>{
        const before=board.revision, saved=await change(data);
        // A comment does not change card fields. Only acknowledge our own
        // activity write when no other writer changed the card in between.
        if(saved && revision===before && board.revision===before+1) {
          revision=board.revision;
          if(drafts.has(card.id)) retainDraft();
        }
        return saved;
      }, error:()=>notice.textContent
    });
    d.refreshActivity=activity.refresh;
    d.addEventListener("close", activity.dispose);
    d.showModal();
    const titleResize=new ResizeObserver(sizeTitle);titleResize.observe(title);
    d.addEventListener('close',()=>titleResize.disconnect());
    title.focus({preventScroll:true});sizeTitle();
  }
  function confirmDelete(ids, previous) {
    const revision = board.revision, d = dialog("Delete " + ids.length + " card" + (ids.length === 1 ? "?" : "s?"));
    d.append(el("p", "This permanently deletes the selected cards. Tasks belonging to deleted milestones are kept and unassigned."), button("Cancel", () => d.close()), button("Delete permanently", async () => {
      if (await change({ action: "delete", ids }, revision)) {
        d.close();
        previous?.close();
      } else error.textContent = notice.textContent;
    }));
    const error = el("p");
    error.setAttribute("role", "alert");
    d.append(error);
    d.showModal();
  }
  search.oninput = () => {
    state.query = search.value;
    render();
  };
  filter.onchange = () => {
    state.filter = filter.value;
    render();
  };
  archived.onchange = () => {
    state.archived = archived.checked;
    picked.clear();
    render();
  };
  refresh();
  const timer = setInterval(() => {
    if (!document.hidden && !busy) refresh();
  }, 2200);
  return () => {
    disposed = true;
    endDrag();
    clearInterval(timer);
    closeContext();contextAbort.abort();outline?.dispose();
    options.sidebar?.replaceChildren();options.onSidebarMode?.(false);
    document.querySelectorAll(".task-dialog").forEach((d) => {
      d.close();
      d.remove();
    });
    root.remove();
  };
}
export {
  fuzzyCard,
  mountTasks
};
