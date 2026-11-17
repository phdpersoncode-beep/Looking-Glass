// AltGr often reports Ctrl+Alt and a physical KeyZ while entering a character.
// Keep the physical-key fallback for macOS Option+Z, without stealing AltGr text.
export function isZenShortcut(event) {
  if (!event.altKey || event.shiftKey || event.isComposing || event.getModifierState?.('AltGraph')) return false;
  return event.key.toLowerCase() === 'z' || (!event.ctrlKey && !event.metaKey && event.code === 'KeyZ');
}
