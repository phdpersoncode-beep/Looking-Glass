import mermaid from 'mermaid';
import DOMPurify from 'dompurify';

let serial=0,configuredTheme=null;
export async function renderDiagram(host,source) {
  if(source.length>30000)throw new Error('Diagram source is limited to 30,000 characters.');
  const theme=document.documentElement.dataset.theme==='dark'?'dark':'default';
  if(configuredTheme!==theme){
    mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme,htmlLabels:false,
      flowchart:{htmlLabels:false},maxTextSize:30000,maxEdges:500,suppressErrorRendering:true});
    configuredTheme=theme;
  }
  const {svg}=await mermaid.render('looking-glass-diagram-'+(++serial),source);
  if(host.isConnected)host.innerHTML=DOMPurify.sanitize(svg,{USE_PROFILES:{svg:true,svgFilters:true}});
}
