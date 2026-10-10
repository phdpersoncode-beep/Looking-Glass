import {StateEffect,StateField} from '@codemirror/state';
import {Decoration,EditorView,WidgetType} from '@codemirror/view';
import {apply,ranges,label,pointLength} from './review-model.mjs';

export const reviewEffect=StateEffect.define();
export const remoteReview=StateEffect.define();
export function operationsFor(transaction){
  const operations=[];
  transaction.changes.iterChanges((from,to,_a,_b,inserted)=>{
    const points=at=>pointLength(transaction.startState.sliceDoc(0,at));
    operations.push({start:points(from),end:points(to),insert:inserted.sliceString(0,inserted.length,transaction.state.lineBreak)});
  });
  // CodeMirror changes share the before-document coordinate system.
  return operations.reverse();
}
class RemovedText extends WidgetType {
  constructor(segment){super();this.segment=segment;}
  eq(other){return JSON.stringify(this.segment)===JSON.stringify(other.segment);}
  toDOM(){
    const el=document.createElement('span');el.className='review-deletion';el.textContent=this.segment.text;
    el.title=label(this.segment);el.dataset.reviewDeletion=String(this.segment.edit_id||'local');el.dataset.reviewFrom=String(this.segment.from);
    el.setAttribute('contenteditable','false');el.tabIndex=0;el.onpointerdown=()=>el.focus({preventScroll:true});return el;
  }
  ignoreEvent(){return true;}
}
function decorations(segments){
  return Decoration.set(ranges(segments,true).map(segment=>segment.kind==='delete'
    ?Decoration.widget({widget:new RemovedText(segment),side:-1}).range(segment.from)
    :Decoration.mark({class:segment.role==='agent'?'review-agent':'review-human',attributes:{title:label(segment)}}).range(segment.from,segment.to)),true);
}
export function reviewTracking(draft,metadata){
  const field=StateField.define({
    create:()=>({segments:draft.segments,decorations:decorations(draft.segments)}),
    update(value,tr){
      let segments=value.segments;
      for(const effect of tr.effects)if(effect.is(reviewEffect))segments=effect.value;
      if(tr.docChanged&&!tr.effects.some(e=>e.is(remoteReview)))segments=apply(segments,operationsFor(tr),metadata(),draft.base);
      return segments===value.segments?value:{segments,decorations:decorations(segments)};
    },
    provide:field=>EditorView.decorations.from(field,value=>value.decorations)
  });
  return field;
}
