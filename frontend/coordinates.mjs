// Raw source uses UTF-16; server offsets use Unicode code points; editors also
// normalize CRLF. Conversions belong at named boundaries, never in rendering.
export function codePointsToEditorUnits(text, points) {
  return Array.from(text).slice(0, points).join('').replace(/\r\n/g, '\n').length;
}
export function editorUnitsToRawUnits(text, units) {
  let at = 0;
  for (let i = 0; i < text.length; i++) {
    if (at === units) return i;
    if (text[i] === '\r' && text[i + 1] === '\n') i++;
    at++;
  }
  return text.length;
}
export function rawUnitsToCodePoints(text, units) {return Array.from(text.slice(0, units)).length;}
export function editorUnitsToCodePoints(text, units) {
  return rawUnitsToCodePoints(text, editorUnitsToRawUnits(text, units));
}
