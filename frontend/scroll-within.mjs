export function scrollWithin(scroller,element){
  const bounds=scroller.getBoundingClientRect(),rect=element.getBoundingClientRect();
  if(rect.top<bounds.top)scroller.scrollTop+=rect.top-bounds.top;
  else if(rect.bottom>bounds.bottom)scroller.scrollTop+=rect.bottom-bounds.bottom;
}
