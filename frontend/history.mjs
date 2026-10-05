// Pure lane layout: carry parent identities through splits, merges, and pages.
export function graphRows(commits,branches=[]) {
  let lanes=[];const rows=[],colors=new Map();
  for(const branch of branches)if(!colors.has(branch.commit))colors.set(branch.commit,branch.ref);
  for(const commit of commits){
    if(!colors.has(commit.hash))colors.set(commit.hash,commit.hash);
    commit.parents.forEach((parent,index)=>{if(!colors.has(parent))colors.set(parent,index===0?colors.get(commit.hash):parent);});
    const before=[...lanes];let column=lanes.indexOf(commit.hash);
    if(column<0){column=lanes.length;lanes.push(commit.hash);}
    const at=[...lanes],parents=[...new Set(commit.parents)];
    lanes.splice(column,1);
    for(const parent of [...parents].reverse())if(!lanes.includes(parent))lanes.splice(column,0,parent);
    const after=[...lanes],edges=[];
    for(let x=0;x<before.length;x++)edges.push({from:x,to:at.indexOf(before[x]),half:'top',key:colors.get(before[x])});
    for(let x=0;x<at.length;x++){
      const targets=x===column?parents:[at[x]];
      for(const target of targets)edges.push({from:x,to:after.indexOf(target),half:'bottom',key:colors.get(target)});
    }
    rows.push({commit,column,edges,color:colors.get(commit.hash),width:Math.max(before.length,at.length,after.length,1)});
  }
  return rows;
}
export function hue(value){let hash=0;for(const ch of value)hash=(hash*31+ch.codePointAt(0))|0;return ((hash%360)+360)%360;}
const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
const color=value=>`hsl(${hue(value)} 52% 52%)`;
export function mountHistory(host,state,api){
  const panel=el('section','history-view');panel.setAttribute('aria-label','Git commit history');
  const tools=el('div','history-tools'),filter=el('details','branch-filter'),summary=el('summary','','Branches'),choices=el('div','branch-options');
  filter.append(summary,choices);const refresh=el('button','','Refresh'),status=el('span','muted'),list=el('div','commit-list');
  list.setAttribute('role','list');const more=el('button','history-more','Load older commits'),detail=el('pre','commit-detail');detail.hidden=true;
  tools.append(filter,refresh,status);panel.append(tools,list,more,detail);host.append(panel);
  let generation=0;
  state.commits??=[];state.selection??=null;state.branches??=[];
  function filters(){
    choices.replaceChildren();const all=el('button','','Show all branches');all.onclick=()=>{state.selection=null;void load();};choices.append(all);
    for(const branch of state.branches){const label=el('label'),check=el('input'),name=el('span','',branch.name);
      check.type='checkbox';check.checked=state.selection===null||state.selection.includes(branch.ref);check.setAttribute('aria-label',branch.name);
      name.style.setProperty('--branch-color',color(branch.ref));name.className='branch-name';label.append(check,name);choices.append(label);
      check.onchange=()=>{const selected=state.selection??state.branches.map(b=>b.ref);state.selection=check.checked?[...selected,branch.ref]:selected.filter(ref=>ref!==branch.ref);void load();};
    }
    summary.textContent=state.selection===null?'All branches':`${state.selection.length} branches`;
  }
  function render(){
    const rows=graphRows(state.commits,state.branches),width=Math.max(1,...rows.map(r=>r.width))*18+16;
    list.replaceChildren();list.style.setProperty('--graph-width',width+'px');
    const tips=new Map();for(const b of state.branches){if(!tips.has(b.commit))tips.set(b.commit,[]);tips.get(b.commit).push(b);}
    for(const {commit,column,edges,color:laneColor} of rows){
      const row=el('button','commit-row');row.type='button';row.dataset.commit=commit.hash;row.setAttribute('role','listitem');row.title=commit.message;
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('width',width);svg.setAttribute('height',60);svg.setAttribute('aria-hidden','true');
      for(const edge of edges){const line=document.createElementNS(svg.namespaceURI,'path'),x=16+edge.from*18,y=16+edge.to*18,top=edge.half==='top';
        line.setAttribute('d',top?`M ${x} 0 C ${x} 18 ${y} 12 ${y} 30`:`M ${x} 30 C ${x} 48 ${y} 42 ${y} 60`);line.setAttribute('fill','none');line.setAttribute('stroke',color(edge.key));line.setAttribute('stroke-width','1.6');svg.append(line);
      }
      const dot=document.createElementNS(svg.namespaceURI,'circle');dot.setAttribute('cx',16+column*18);dot.setAttribute('cy',30);dot.setAttribute('r',4);dot.setAttribute('fill','var(--paper)');dot.setAttribute('stroke',color(laneColor));dot.setAttribute('stroke-width','2');svg.append(dot);
      const content=el('span','commit-content'),subject=el('span','commit-subject',commit.subject),meta=el('span','commit-meta');
      const author=el('span','commit-author',commit.committer),mark=el('span','author-mark',([...commit.committer][0]||'?').toUpperCase());mark.style.background=color(commit.committer_email||commit.committer);
      author.prepend(mark);author.title=commit.author===commit.committer?`${commit.committer} <${commit.committer_email}>`:`Committed by ${commit.committer} <${commit.committer_email}> · Authored by ${commit.author} <${commit.author_email}>`;
      const date=el('time','',new Date(commit.date).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}));date.dateTime=commit.date;
      meta.append(author,el('code','',commit.hash.slice(0,8)),date);
      const badges=el('span','branch-badges');for(const branch of tips.get(commit.hash)||[]){const badge=el('span','branch-badge',branch.name);badge.style.setProperty('--branch-color',color(branch.ref));badges.append(badge);}
      content.append(subject,meta);row.append(svg,content,badges);
      row.onclick=()=>{for(const other of list.children)other.classList.toggle('selected',other===row);detail.hidden=false;detail.textContent=`${commit.hash}\nCommitted by ${commit.committer} <${commit.committer_email}>\nAuthored by ${commit.author} <${commit.author_email}>\n${commit.date}\n\n${commit.message}`;};list.append(row);
    }
    if(!rows.length)list.append(el('p','history-empty',state.repository===false?'This workspace has no Git repository.':state.selection?.length===0?'Choose a branch to see its history.':'No commits yet.'));
    more.hidden=state.next_offset==null;status.textContent=`${state.commits.length} commits · newest first`;
  }
  async function load(append=false){
    const request=++generation;more.disabled=true;status.textContent='Loading…';
    const query=new URLSearchParams({limit:100,offset:append?state.next_offset:0});
    if(state.selection!==null){if(!state.selection.length){state.commits=[];state.next_offset=null;render();filters();return;}for(const ref of state.selection)query.append('branch',ref);}
    if(append)for(const tip of state.tips||[])query.append('tip',tip);
    try{const data=await api('git/history?'+query);if(request!==generation||!panel.isConnected)return;
      Object.assign(state,{...data,commits:append?[...state.commits,...data.commits]:data.commits});filters();render();
    }catch(error){if(request===generation)status.textContent=error.message;}
    finally{if(request===generation)more.disabled=false;}
  }
  refresh.onclick=()=>{detail.hidden=true;void load();};more.onclick=()=>void load(true);
  filters();render();if(!state.commits.length)void load();
  return ()=>{generation++;};
}
