import {createThreadSearch} from './thread-search.mjs';
import {compareThreadPosition,threadEligible} from './app-state.mjs';
import {scrollWithin} from './scroll-within.mjs';

function appendExcerpt(host,{text,ranges,leading,trailing}){
  let at=0;
  if(leading)host.append('…');
  for(const [from,to] of ranges){
    host.append(text.slice(at,from));
    const mark=document.createElement('mark');mark.textContent=text.slice(from,to);host.append(mark);
    at=to;
  }
  host.append(text.slice(at));
  if(trailing)host.append('…');
}

export function createThreadSearchView(sidebar,{onInput,onOpen,onRefresh,loadIndex}) {
  const input=sidebar.querySelector('#thread-search'),clear=sidebar.querySelector('#thread-search-clear');
  const status=sidebar.querySelector('#thread-search-status'),empty=sidebar.querySelector('#thread-search-empty');
  const host=sidebar.querySelector('#threads'),scroller=sidebar.querySelector('.discussion-content');
  const hints=sidebar.querySelector('#thread-search-hints'),scope=sidebar.querySelector('#thread-scope'),resolved=sidebar.querySelector('#show-resolved');
  const area=input.closest('.thread-search-area'),picker=area.querySelector('#thread-picker');
  const list=picker.querySelector('[role=listbox]'),pickerStatus=picker.querySelector('[role=status]');
  let indexed=null,search=()=>[],results=[],listScroll=0,searching=false;
  let eligible=[],eligibleById=new Map(),pickerDocument=null,renderedPicker=null,selected=null;
  let globalThreads=[],globalSearch=()=>[],hintTag=null,hintTime=0,hintLoading=false;
  let context=null;
  async function refreshHints(){
    if(hintLoading||Date.now()-hintTime<2000)return;
    const requestedContext=context;
    hintLoading=true;hintTime=Date.now();
    try{
      const result=await loadIndex(hintTag,requestedContext);
      if(context!==requestedContext)return;
      hintTag=result.etag;
      if(result.data){globalThreads=result.data;globalSearch=createThreadSearch(globalThreads);}
      onRefresh();
    }catch{/* Hint discovery should never interrupt the local search. */}
    finally{if(context===requestedContext)hintLoading=false;}
  }
  function hint(count,label,enableScope,enableResolved,disableOnlyUnattached=false){
    if(!count)return;
    const button=document.createElement('button');button.type='button';button.textContent=`${count} ${count===1?'match':'matches'} ${label}`;
    button.onclick=()=>{if(enableResolved&&!resolved.checked)resolved.click();if(enableScope&&!scope.checked)scope.click();if(disableOnlyUnattached)sidebar.querySelector('#only-unattached').click();};hints.append(button);
  }
  function selectOption(option){
    if(selected!==option)selected?.setAttribute('aria-selected','false');
    selected=option;
    if(option){
      option.setAttribute('aria-selected','true');
      input.setAttribute('aria-activedescendant',option.id);
      scrollWithin(list,option);
    }else input.removeAttribute('aria-activedescendant');
  }
  function renderPicker(){
    if(picker.hidden)return;
    const query=input.value.trim(),across=scope.checked;
    const ids=eligible.map(t=>t.id).join(',');
    if(renderedPicker?.threads===indexed&&renderedPicker.ids===ids&&renderedPicker.query===query&&renderedPicker.across===across)return;
    const keep=renderedPicker?.query===query?selected?.id:null;
    renderedPicker={threads:indexed,ids,query,across};
    const matches=new Map(results.map(result=>[result.id,result]));
    const ordered=query?results.map(result=>eligibleById.get(result.id)):eligible.slice().sort(compareThreadPosition);
    const fragment=document.createDocumentFragment();
    for(const thread of ordered){
      const button=document.createElement('button');button.type='button';button.tabIndex=-1;
      button.id='thread-option-'+thread.id;button.dataset.threadOption=thread.id;
      button.setAttribute('role','option');button.setAttribute('aria-selected','false');
      const number=document.createElement('span');number.className='thread-option-number';number.textContent='#'+thread.id;
      const label=document.createElement('span');label.className='search-match-label';
      const match=matches.get(thread.id);
      label.textContent=[match?.label,across?thread.path:null].filter(Boolean).join(' · ');
      const excerpt=document.createElement('span');excerpt.className='search-match-excerpt';
      if(match)appendExcerpt(excerpt,match.excerpt);
      else{
        const summary=String(thread.messages?.[0]?.body||thread.quote||'').replace(/\s+/gu,' ').trim();
        excerpt.textContent=summary.length>150?summary.slice(0,150)+'…':summary;
      }
      button.append(number);
      if(label.textContent)button.append(label);
      button.append(excerpt);fragment.append(button);
    }
    list.replaceChildren(fragment);
    pickerStatus.hidden=!!ordered.length;
    pickerStatus.textContent=ordered.length?'':query?'No matching threads.':'No threads in this view.';
    selectOption(keep?document.getElementById(keep):null);
    if(!selected)list.scrollTop=0;
  }
  function openPicker(){
    if(!picker.hidden)return;
    picker.hidden=false;
    input.setAttribute('aria-expanded','true');
    renderPicker();
  }
  function closePicker(){
    if(picker.hidden)return;
    picker.hidden=true;
    input.setAttribute('aria-expanded','false');
    selectOption(null);renderedPicker=null;
  }
  function choose(option){if(option){closePicker();onOpen(Number(option.dataset.threadOption));}}
  function changed(){
    const next=!!input.value.trim();
    if(next&&!searching)listScroll=scroller.scrollTop;
    searching=next;onInput();scroller.scrollTop=next?0:listScroll;
  }
  function reset(){
    input.focus({preventScroll:true});
    closePicker();
    input.value='';
    changed();
  }
  input.addEventListener('input',()=>{changed();openPicker();});
  input.addEventListener('focus',openPicker);
  area.querySelector('.thread-search-bar').addEventListener('click',event=>{
    if(clear.contains(event.target))return;
    input.focus({preventScroll:true});
    openPicker();
  });
  clear.addEventListener('click',reset);
  list.addEventListener('mousedown',event=>{if(event.target.closest('[role=option]'))event.preventDefault();});
  list.addEventListener('click',event=>choose(event.target.closest('[role=option]')));
  document.addEventListener('click',event=>{if(!area.contains(event.target))closePicker();});
  const buttons=()=>results.map(r=>host.querySelector(`.thread[data-thread="${r.id}"]>.thread-search-match`)).filter(b=>b&&!b.closest('.thread').hidden);
  function focusResult(button){if(button){button.focus({preventScroll:true});scrollWithin(scroller,button);}}
  input.addEventListener('keydown',event=>{
    if(event.defaultPrevented||event.isComposing)return;
    if(event.key==='Tab'){closePicker();return;}
    if(event.key==='Escape'&&(!picker.hidden||input.value)){
      event.preventDefault();event.stopPropagation();
      if(input.value)reset();
      else closePicker();
    }
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){
      event.preventDefault();openPicker();
      const forward=event.key==='ArrowDown';
      const option=selected
        ?(forward?selected.nextElementSibling:selected.previousElementSibling)
        :(forward?list.firstElementChild:list.lastElementChild);
      if(option)selectOption(option);
    }
    if(event.key==='Enter'){
      event.preventDefault();openPicker();choose(selected||list.firstElementChild);
    }
  });
  host.addEventListener('keydown',event=>{
    if(!event.target.matches('.thread-search-match')||event.defaultPrevented)return;
    const list=buttons(),at=list.indexOf(event.target);
    if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();focusResult(list[(at+(event.key==='ArrowDown'?1:-1)+list.length)%list.length]);}
    if(event.key==='Escape'){event.preventDefault();input.focus({preventScroll:true});}
  });
  host.addEventListener('click',event=>{
    const button=event.target.closest('.thread-search-match');
    if(button){event.preventDefault();onOpen(Number(button.closest('.thread').dataset.thread));}
  });
  function update(state,nextContext){
    const {threads,spotlightIds,showResolved,onlyUnattached,onlyUnread,isUnread,displayedDocument}=state;
    if(pickerDocument!==displayedDocument){pickerDocument=displayedDocument;closePicker();}
    if(context!==nextContext){context=nextContext;globalThreads=[];globalSearch=()=>[];hintTag=null;hintTime=0;hintLoading=false;}
    if(indexed!==threads){indexed=threads;search=createThreadSearch(threads);}
    const query=input.value.trim(),enabled=!!query&&!spotlightIds.length;
    const back=sidebar.querySelector('#all-discussions');back.firstChild.textContent=query?'Search results ':'All discussions ';back.title=(query?'Search results':'All discussions')+' (Esc)';
    eligible=threads.filter(t=>threadEligible(t,state));
    eligibleById=new Map(eligible.map(t=>[t.id,t]));
    results=query?search(query).filter(result=>eligibleById.has(result.id)):[];
    renderPicker();
    clear.hidden=!input.value;status.hidden=!enabled;empty.hidden=!enabled||!!results.length;
    status.textContent=`${results.length} ${results.length===1?'match':'matches'} · Best matches first`;
    hints.replaceChildren();
    if(enabled&&!results.length){
      const localIds=new Set(threads.map(t=>t.id));
      const all=scope.checked?threads:[...globalThreads.filter(t=>!localIds.has(t.id)),...threads];
      const byId=new Map(all.map(t=>[t.id,t]));
      // The current scope is authoritative even while the global hint cache loads.
      const found=new Set([...search(query).map(r=>r.id),...(!scope.checked?globalSearch(query).filter(r=>!localIds.has(r.id)).map(r=>r.id):[])]);
      const counts=new Map();
      for(const id of found){
        const t=byId.get(id);if(!t||onlyUnread&&!isUnread(t))continue;
        const mask=(!scope.checked&&!localIds.has(id)?1:0)|(t.resolved&&!showResolved?2:0)|(onlyUnattached&&t.anchor_status==='attached'?4:0);
        if(mask)counts.set(mask,(counts.get(mask)||0)+1);
      }
      for(const [mask,count] of counts){
        const outside=!!(mask&1),closed=!!(mask&2),attached=!!(mask&4);
        const label=attached?`in ${closed?'resolved attached':'attached'} threads${outside?' in other files':''}`
          :closed?`in resolved threads${outside?' in other files':''}`:'in other files';
        hint(count,label,outside,closed,attached);
      }
      if(!scope.checked&&!onlyUnread)refreshHints();
    }
    sidebar.classList.toggle('thread-searching',enabled);
    const matches=new Map(results.map(result=>[result.id,result]));
    const cards=new Map([...host.querySelectorAll(':scope>.thread')].map(card=>[Number(card.dataset.thread),card]));
    for(const [id,card] of cards){
      const result=enabled?matches.get(id):null;
      let button=card.querySelector(':scope>.thread-search-match');
      if(!result){if(button)button.hidden=true;continue;}
      const key=JSON.stringify(result);
      if(!button){button=document.createElement('button');button.type='button';button.className='thread-search-match';card.insertBefore(button,card.querySelector('.thread-body'));}
      button.hidden=false;if(button.dataset.match===key)continue;
      button.dataset.match=key;button.setAttribute('aria-label',`Open thread #${id}, matched ${result.label.toLowerCase()}`);
      const label=document.createElement('span');label.className='search-match-label';label.textContent=result.label+(sidebar.querySelector('#thread-scope').checked?' · '+card.dataset.path:'');
      const excerpt=document.createElement('span');excerpt.className='search-match-excerpt';
      appendExcerpt(excerpt,result.excerpt);
      button.replaceChildren(label,excerpt);
    }
    // Move existing cards only when needed, preserving reply drafts and focus.
    const ordered=enabled?[...results.map(r=>r.id),...threads.filter(t=>!matches.has(t.id)).map(t=>t.id)]:threads.map(t=>t.id);
    let cursor=host.firstElementChild;
    for(const id of ordered){const card=cards.get(id);if(!card)continue;if(card!==cursor)host.insertBefore(card,cursor);else cursor=cursor.nextElementSibling;}
    const placeholder=host.querySelector('.empty-discussions');if(placeholder)placeholder.hidden=enabled||onlyUnread;
    return enabled?matches:null;
  }
  return {update,closePicker};
}
