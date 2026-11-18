import {iconButton} from './icons.mjs';

export function cardTitle(card) {
  return card.milestone ? `M${card.milestone_number}: ${card.title}` : card.title;
}

// Keep ordering independent of the Kanban columns. Hidden ancestors are retained
// as context so an archived parent never makes an active descendant disappear.
export function outlineRows(cards, {rootId = null, archived = false, folded = new Set(), collapsed = false} = {}) {
  const byId = new Map(cards.map(c => [c.id, c])), included = new Set();
  for (const card of cards) if (!!card.archived === archived) {
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
      rows.push({card, depth, children: children.get(card.id)?.length || 0, context: !!card.archived !== archived});
      if (!collapsed && !folded.has(card.id)) visit(card.id, depth+1);
    }
  }
  visit(rootId, 0);
  return rows;
}

export function shiftTarget(cards, id, outdent = false) {
  const card = cards.find(c => c.id === id);
  if (!card || card.milestone) return null;
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

const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};

export function mountTaskOutline(host, options) {
  const {getBoard, state, picked, write, open, contextMenu, changed, create, rootId = null} = options;
  const drafts = state.outlineDrafts ??= new Map(), views = state.outlineViews ??= new Map();
  const key=rootId??'plan', view=views.get(key)||{collapsed:false};views.set(key,view);
  const section = element('section', undefined, 'task-outline'), list = element('div', undefined, 'task-outline-list'), status = element('div', undefined, 'task-outline-status');
  section.setAttribute('aria-label', rootId ? 'Card tasks' : 'Task hierarchy');
  list.setAttribute('role','list');
  status.setAttribute('role','status');
  const add = element('button', '+ Add ' + (rootId ? 'subitem' : 'task'), 'task-outline-add');
  add.type='button';add.onclick=()=>create(rootId);
  const controls=element('div',undefined,'task-outline-controls');
  controls.setAttribute('role','group');controls.setAttribute('aria-label','Task list display');
  const collapse=iconButton('Collapse all tasks','collapse',()=>{view.collapsed=true;render();});
  const expand=iconButton('Expand all tasks','expand',()=>{view.collapsed=false;render();});
  controls.append(collapse,expand);
  if(rootId){const heading=element('div',undefined,'task-outline-heading');heading.append(element('h3','Tasks'),controls);section.append(heading);}
  else (options.controlsHost||section).append(controls);
  section.append(list, add, status);host.append(section);
  const nodes = new Map();
  let rows = [], drag = null, disposed = false, rendering = false, saving = Promise.resolve();

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
  async function shift(id, outdent) {
    if(!await saveName(id))return;
    const target=shiftTarget(getBoard().cards,id,outdent);
    if(target && await mutate({action:'outline_move',ids:picked.has(id)?[...picked]:[id],...target})) focusRow(id);
  }
  function nextFocus(id, direction) {
    const index=rows.findIndex(r=>r.card.id===id);
    focusRow(rows[index+direction]?.card.id);
  }
  function makeRow(id) {
    const row=element('div',undefined,'task-outline-row');row.dataset.id=id;row.setAttribute('role','listitem');row.draggable=true;
    const check=element('input');check.type='checkbox';check.className='task-outline-check';
    check.onchange=async()=>{check.disabled=true;if(!await mutate({action:'update',ids:[id],changes:{status:check.checked?'done':'backlog'}}))check.checked=!check.checked;check.disabled=false;};
    const reference=element('button',undefined,'task-outline-reference');reference.type='button';reference.onclick=()=>openCard(id);
    const prefix=element('span',undefined,'task-outline-prefix'), name=element('input',undefined,'task-outline-name');
    name.type='text';name.maxLength=500;name.draggable=false;
    name.oninput=()=>{const previous=drafts.get(id);drafts.set(id,{value:name.value,revision:previous?.revision??getBoard().revision});};
    name.onblur=()=>{if(!rendering)saveName(id);};
    name.onkeydown=async event=>{
      if(event.key==='Tab') {
        if(!name.readOnly && shiftTarget(getBoard().cards,id,event.shiftKey)) {
          event.preventDefault();await shift(id,event.shiftKey);
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
        if(event.altKey) {
          const card=getBoard().cards.find(c=>c.id===id),siblings=rows.filter(r=>r.card.parent_id===card.parent_id).map(r=>r.card);
          const at=siblings.findIndex(c=>c.id===id), target=direction<0?siblings[at-1]:siblings[at+2];
          if(!card.milestone && (direction>0?at<siblings.length-1:at>0))await mutate({action:'outline_move',ids:[id],parent_id:card.parent_id,before:target?.id??null});
          focusRow(id);
        } else nextFocus(id,direction);
      }
    };
    const pen=iconButton('Edit card '+id,'pen',()=>openCard(id));
    pen.classList.add('task-outline-pen');
    row.append(check,reference,prefix,name,pen);
    row.addEventListener('click',event=>{
      if(event.ctrlKey||event.metaKey) {event.preventDefault();event.stopPropagation();picked.has(id)?picked.delete(id):picked.add(id);changed();}
    },true);
    row.oncontextmenu=event=>contextMenu(event,id);
    row.ondragstart=event=>{
      if(event.target===name){event.preventDefault();return;}
      const ids=picked.has(id)?[...picked]:[id];
      drag={id,ids,x:event.clientX};
      event.dataTransfer.setData('application/x-looking-glass-cards',JSON.stringify(drag));
      event.dataTransfer.setData('text/plain',String(id));event.dataTransfer.effectAllowed='move';
      row.classList.add('task-outline-dragging');
    };
    row.ondragend=()=>{drag=null;clearDrop();row.classList.remove('task-outline-dragging');};
    row.ondragover=event=>{
      if(!event.dataTransfer.types.includes('application/x-looking-glass-cards'))return;
      event.preventDefault();event.stopPropagation();clearDrop();
      const card=getBoard().cards.find(c=>c.id===id), source=drag||{};
      const delta=event.clientX-(source.x??event.clientX);
      row.dataset.drop=delta>24||card.milestone?'inside':delta < -24?'outside':event.clientY>row.getBoundingClientRect().top+row.offsetHeight/2?'after':'before';
      event.dataTransfer.dropEffect='move';
    };
    row.ondrop=async event=>{
      event.preventDefault();event.stopPropagation();
      let source;try{source=JSON.parse(event.dataTransfer.getData('application/x-looking-glass-cards'));}catch{return;}
      const mode=row.dataset.drop;clearDrop();
      const card=getBoard().cards.find(c=>c.id===id);if(!card||!Array.isArray(source.ids))return;
      let target;
      if(source.id===id)target=shiftTarget(getBoard().cards,id,mode==='outside');
      else if(mode==='inside')target={parent_id:id,before:null};
      else if(mode==='outside')target=shiftTarget(getBoard().cards,id,true);
      else {
        const siblings=rows.filter(r=>r.card.parent_id===card.parent_id).map(r=>r.card);
        target={parent_id:card.parent_id,before:mode==='after'?(siblings[siblings.indexOf(card)+1]?.id??null):id};
      }
      if(target)await mutate({action:'outline_move',ids:source.ids,...target});
    };
    return row;
  }
  function clearDrop(){for(const row of nodes.values())delete row.dataset.drop;}
  function render() {
    if(disposed)return;
    rendering=true;
    const focused=section.contains(document.activeElement)?document.activeElement:null;
    const selection=focused?.matches('input[type=text]')?[focused.selectionStart,focused.selectionEnd]:null;
    rows=outlineRows(getBoard().cards,{rootId,archived:!!state.archived,collapsed:view.collapsed});
    const allRows=view.collapsed?outlineRows(getBoard().cards,{rootId,archived:!!state.archived}):rows;
    collapse.disabled=view.collapsed||!allRows.some(r=>r.children);
    expand.disabled=!view.collapsed;
    collapse.setAttribute('aria-pressed',String(view.collapsed));expand.setAttribute('aria-pressed',String(!view.collapsed));
    const visible=new Set(rows.map(r=>r.card.id));
    for(const [id,row] of nodes)if(!visible.has(id)){row.remove();nodes.delete(id);}
    for(let index=0;index<rows.length;index++) {
      const {card,depth,children,context}=rows[index];
      let row=nodes.get(card.id);if(!row){row=makeRow(card.id);nodes.set(card.id,row);}
      row.style.setProperty('--task-depth',depth);row.dataset.depth=depth;
      row.classList.toggle('task-outline-milestone',!!card.milestone);row.classList.toggle('task-outline-done',card.status==='done');row.classList.toggle('task-outline-context',context);
      row.setAttribute('aria-selected',String(picked.has(card.id)));row.draggable=!card.archived;
      const [check,reference,prefix,name,pen]=row.children;
      if(children)row.setAttribute('aria-expanded',String(!view.collapsed));else row.removeAttribute('aria-expanded');
      check.checked=card.status==='done';check.disabled=context;check.setAttribute('aria-label','Complete '+card.title);
      reference.textContent=card.milestone?'◇':'#C'+String(card.id).padStart(2,'0');reference.title='Open '+cardTitle(card);reference.setAttribute('aria-label','Open '+(card.milestone?'#M'+card.milestone_number:reference.textContent));
      prefix.textContent=card.milestone?'M'+card.milestone_number+':':'';prefix.hidden=!card.milestone;
      if(!drafts.has(card.id))name.value=card.title;
      else if(document.activeElement!==name)name.value=drafts.get(card.id).value;
      name.readOnly=context;name.setAttribute('aria-label','Task name '+card.id);name.title=cardTitle(card);
      pen.setAttribute('aria-label','Edit '+card.title);pen.title='Edit '+card.title;
      if(list.children[index]!==row)list.insertBefore(row,list.children[index]||null);
    }
    for(const id of drafts.keys())if(!getBoard().cards.some(c=>c.id===id))drafts.delete(id);
    if(focused?.isConnected&&document.activeElement!==focused){focused.focus({preventScroll:true});if(selection)focused.setSelectionRange(...selection);}
    rendering=false;
  }
  render();
  return {render,dispose(){disposed=true;controls.remove();section.remove();},focus:focusRow};
}
