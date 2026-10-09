import {createThreadSearch} from './thread-search.mjs';

export function createThreadSearchView(sidebar,{onInput,onOpen}) {
  const input=sidebar.querySelector('#thread-search'),clear=sidebar.querySelector('#thread-search-clear');
  const status=sidebar.querySelector('#thread-search-status'),empty=sidebar.querySelector('#thread-search-empty');
  const host=sidebar.querySelector('#threads'),scroller=sidebar.querySelector('.discussion-content');
  let indexed=null,search=()=>[],results=[],listScroll=0,searching=false;
  function changed(){
    const next=!!input.value.trim();
    if(next&&!searching)listScroll=scroller.scrollTop;
    searching=next;onInput();scroller.scrollTop=next?0:listScroll;
  }
  function reset(){input.value='';changed();input.focus({preventScroll:true});}
  input.addEventListener('input',changed);clear.addEventListener('click',reset);
  const buttons=()=>results.map(r=>host.querySelector(`.thread[data-thread="${r.id}"]>.thread-search-match`)).filter(b=>b&&!b.closest('.thread').hidden);
  function focusResult(button){
    if(!button)return;button.focus({preventScroll:true});
    const rect=button.getBoundingClientRect(),bounds=scroller.getBoundingClientRect();
    if(rect.top<bounds.top)scroller.scrollTop+=rect.top-bounds.top;else if(rect.bottom>bounds.bottom)scroller.scrollTop+=rect.bottom-bounds.bottom;
  }
  input.addEventListener('keydown',event=>{
    if(event.defaultPrevented)return;
    if(event.key==='Escape'&&input.value){event.preventDefault();event.stopPropagation();reset();}
    if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();const list=buttons();focusResult(event.key==='ArrowDown'?list[0]:list.at(-1));}
    if(event.key==='Enter'&&results.length){event.preventDefault();onOpen(results[0].id);}
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
  function update(threads,spotlight,showResolved){
    if(indexed!==threads){indexed=threads;search=createThreadSearch(threads);}
    const query=input.value.trim(),enabled=!!query&&!spotlight;
    const ids=new Set(threads.filter(t=>showResolved||!t.resolved).map(t=>t.id));
    results=query?search(query).filter(result=>ids.has(result.id)):[];
    clear.hidden=!input.value;status.hidden=!enabled;empty.hidden=!enabled||!!results.length;
    status.textContent=`${results.length} ${results.length===1?'match':'matches'} · Best matches first`;
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
      const {text,ranges,leading,trailing}=result.excerpt;let at=0;
      if(leading)excerpt.append('…');
      for(const [from,to] of ranges){excerpt.append(text.slice(at,from));const mark=document.createElement('mark');mark.textContent=text.slice(from,to);excerpt.append(mark);at=to;}
      excerpt.append(text.slice(at));if(trailing)excerpt.append('…');
      button.replaceChildren(label,excerpt);
    }
    // Move existing cards only when needed, preserving reply drafts and focus.
    const ordered=enabled?[...results.map(r=>r.id),...threads.filter(t=>!matches.has(t.id)).map(t=>t.id)]:threads.map(t=>t.id);
    let cursor=host.firstElementChild;
    for(const id of ordered){const card=cards.get(id);if(!card)continue;if(card!==cursor)host.insertBefore(card,cursor);else cursor=cursor.nextElementSibling;}
    const placeholder=host.querySelector('.empty-discussions');if(placeholder)placeholder.hidden=enabled;
    return enabled?matches:null;
  }
  return {update,get query(){return input.value.trim();},get results(){return results;}};
}
