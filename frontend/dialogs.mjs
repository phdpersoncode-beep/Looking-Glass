import {icon,iconButton} from './icons.mjs';

// Application-owned dialogs: asynchronous, themed, keyboard accessible, and safe
// to stack above an image editor. Errors keep the form and typed value intact.
function show({title,message,value,label='Name',confirmLabel='Confirm',symbol='check',danger=false,onSubmit}){
  return new Promise(resolve=>{
    const previous=document.activeElement,dialog=document.createElement('dialog'),form=document.createElement('form');
    dialog.className='lg-dialog';dialog.setAttribute('aria-label',title);form.noValidate=true;
    const heading=document.createElement('h2');heading.append(icon(symbol),document.createTextNode(title));form.append(heading);
    if(message){const description=document.createElement('p');description.textContent=message;form.append(description);}
    let input;
    if(value!==undefined){const field=document.createElement('label');field.textContent=label;input=document.createElement('input');input.value=value;input.required=true;field.append(input);form.append(field);}
    const error=document.createElement('p');error.className='dialog-error';error.setAttribute('role','alert');
    const actions=document.createElement('div');actions.className='dialog-actions';
    const cancel=iconButton('Cancel','close',()=>dialog.close()),accept=iconButton(confirmLabel,symbol);accept.type='submit';accept.classList.add(danger?'danger':'primary');
    actions.append(cancel,accept);form.append(error,actions);dialog.append(form);document.body.append(dialog);
    let result=null,busy=false;
    form.onsubmit=async event=>{
      event.preventDefault();if(busy)return;
      const text=input?.value.trim();if(input&&!text){error.textContent='Enter a name.';input.focus();return;}
      busy=true;accept.disabled=cancel.disabled=true;error.textContent='';
      try{await onSubmit?.(text);result=input?text:true;dialog.close();}
      catch(e){error.textContent=e.message;}
      finally{busy=false;accept.disabled=cancel.disabled=false;}
    };
    dialog.oncancel=event=>{event.preventDefault();if(!busy)dialog.close();};
    dialog.onclose=()=>{dialog.remove();if(previous?.isConnected)previous.focus({preventScroll:true});resolve(result);};
    dialog.showModal();if(input){input.focus();input.select();}else cancel.focus();
  });
}
export const confirmAction=options=>show(options).then(Boolean);
export const requestText=options=>show({...options,confirmLabel:options.confirmLabel||'Save name',symbol:'pen'});
