// Match the quiet, 20px line symbols used by the discussion controls.
const paths={
  pen:'m4 13-1 4 4-1L17 6l-3-3zM12 5l3 3',
  trash:'M3 5h14M7 5V3h6v2M5 5l1 12h8l1-12M8 8v6M12 8v6',
  comment:'M3 3h14v10H8l-5 4z',
  check:'m4 10 4 4 8-8',
  copy:'M7 9a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2zM13 7V3H3v10h4',
  close:'m5 5 10 10M15 5 5 15',
  undo:'M7 4 3 8l4 4M3 8h8a5 5 0 0 1 0 10',
  redo:'m13 4 4 4-4 4M17 8H9a5 5 0 0 0 0 10',
  restore:'M4 7a6 6 0 1 1-1 6M4 3v4h4',
  eraser:'m3 11 8-8 6 6-8 8H7zM7 7l6 6M9 17h8',
  send:'m3 3 14 7-14 7 3-7zM6 10h11',
  code:'m7 5-5 5 5 5M13 5l5 5-5 5',
  resize:'M17 10v7h-7M17 17l-8-8',
  save:'M4 3h10l3 3v11H3V3h1M6 3v5h8V3M6 17v-6h8v6',
  paperclip:'m7 11 5-5a2 2 0 0 1 3 3l-7 7a3 3 0 0 1-4-4l8-8',
  clearFilter:'M2 3h16l-6 7v3m-4 4v-7L2 3m10 12 5 4m0-4-5 4',
  order:'M3 4v12m-2-3 2 3 3-3M8 5h9M8 10h7M8 15h5',
  sound:'M3 8h3l4-4v12l-4-4H3zM13 7a5 5 0 0 1 0 6m2-9a9 9 0 0 1 0 12',
  muted:'M3 8h3l4-4v12l-4-4H3zM13 8l5 5m0-5-5 5',
  archive:'M3 3h14v4H3zM4 7v10h12V7M8 10h4',
  milestone:'m10 2 8 8-8 8-8-8z',
  addMilestone:'m8 3 5 5-5 5-5-5zM13 15h6m-3-3v6',
  triangle:'m7 4 7 6-7 6z',
  collapse:'M6 3H4a1 1 0 0 0-1 1v10M7 6h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1M9 11.5h5',
  expand:'M6 3H4a1 1 0 0 0-1 1v10M7 6h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1M9 11.5h5m-2.5-2.5v5',
};
export function icon(name){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  for(const [key,value] of Object.entries({viewBox:'0 0 20 20',width:20,height:20,fill:'none',stroke:'currentColor','stroke-width':1.5,'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',paths[name]||paths.check);svg.append(path);return svg;
}
export function iconButton(label,name,action){
  const button=document.createElement('button');button.type='button';button.className='icon-button';button.title=label;button.setAttribute('aria-label',label);button.append(icon(name));button.onclick=action;return button;
}
