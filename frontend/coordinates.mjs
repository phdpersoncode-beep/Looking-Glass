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

// Batch shared source boundaries once for a dense discussion set.
export function sourceCoordinates(text, points) {
  const requested = new Set(points.filter(Number.isInteger)), raw = new Map(), editor = new Map();
  let point = 0, rawAt = 0, editorAt = 0, previous = '';
  const record = () => {if (requested.has(point)) {raw.set(point, rawAt); editor.set(point, editorAt);}};
  record();
  for (const character of text) {
    rawAt += character.length;
    if (character !== '\n' || previous !== '\r') editorAt += character.length;
    point++; record(); previous = character;
  }
  return {raw, editor, length: point};
}

export function replacementFor(before, after) {
  let start = 0, end = before.length, nextEnd = after.length;
  while (start < end && start < nextEnd && before[start] === after[start]) start++;
  while (end > start && nextEnd > start && before[end - 1] === after[nextEnd - 1]) {end--; nextEnd--;}
  const inside = (text, at) => at > 0 && at < text.length && (
    /[\uD800-\uDBFF]/.test(text[at - 1]) && /[\uDC00-\uDFFF]/.test(text[at]) || text[at - 1] === '\r' && text[at] === '\n');
  if (inside(before, start) || inside(after, start)) start--;
  if (inside(before, end) || inside(after, nextEnd)) {end++; nextEnd++;}
  return {from: codePointsToEditorUnits(before, rawUnitsToCodePoints(before, start)),
    to: codePointsToEditorUnits(before, rawUnitsToCodePoints(before, end)), insert: after.slice(start, nextEnd)};
}
