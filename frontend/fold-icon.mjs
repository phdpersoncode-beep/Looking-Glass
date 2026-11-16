// Use the same stacked-panel geometry as the explorer/discussion controls.
export function foldIcon(expand,size=14){
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');
  for(const [key,value] of Object.entries({width:size,height:size,viewBox:'0 0 20 20',fill:'none',stroke:'currentColor','stroke-width':1.4,'stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
  for(const [tag,attrs] of [['path',{d:'M6 3H4a1 1 0 0 0-1 1v10'}],['rect',{x:6,y:6,width:11,height:11,rx:2}],['path',{d:expand?'M9 11.5h5m-2.5-2.5v5':'M9 11.5h5'}]]){
    const el=document.createElementNS(ns,tag);for(const [key,value] of Object.entries(attrs))el.setAttribute(key,value);svg.append(el);
  }
  return svg;
}
