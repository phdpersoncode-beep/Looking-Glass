// Native dialogs report backdrop pointer events on the dialog itself. Check
// both ends of the gesture so selecting text out of the window never closes it.
export function bindTaskDismiss(dialog, dismiss) {
  let startedOutside = false;
  const outside = event => {
    const rect = dialog.getBoundingClientRect();
    return event.target === dialog && (event.clientX < rect.left || event.clientX >= rect.right || event.clientY < rect.top || event.clientY >= rect.bottom);
  };
  dialog.addEventListener('pointerdown', event => { startedOutside = event.button === 0 && outside(event); });
  dialog.addEventListener('pointercancel', () => { startedOutside = false; });
  dialog.addEventListener('click', event => {
    const close = startedOutside && outside(event);startedOutside = false;
    if(close){event.preventDefault();dismiss();}
  });
  dialog.addEventListener('cancel', event => {event.preventDefault();dismiss();});
}
