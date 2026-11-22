import {countColumn} from '@codemirror/state';
import {syntaxTree} from '@codemirror/language';
import {EditorView, ViewPlugin} from '@codemirror/view';

const definitionNames = new Set(['ClassDefinition', 'FunctionDefinition']);
const leadingSpace = text => /^[ \t\f]*/.exec(text)[0];

// These offsets are CodeMirror document positions, including in CRLF files.
export function pythonScopesAt(tree, doc, position) {
  if (tree.length < position) return [];
  let line = doc.lineAt(position);
  const space = leadingSpace(line.text);
  let offset = Math.max(position, line.from + space.length);
  let side = offset === line.to && line.length ? -1 : 1;
  let blankIndent = null;
  if (space && space.length === line.length) {
    blankIndent = countColumn(space, 8);
    while (line.number > 1 && !line.text.trim()) line = doc.line(line.number - 1);
    offset = line.to;
    side = -1;
  }
  if (tree.length < offset) return [];

  const scopes = [];
  for (let node = tree.resolveInner(offset, side); node; node = node.parent) {
    let definition = node;
    if (node.name === 'DecoratedStatement' && offset < node.lastChild?.from) definition = node.lastChild;
    if (!definitionNames.has(definition.name)) continue;
    const name = definition.getChild('VariableName');
    if (!name) continue;
    const headerLine = doc.lineAt(definition.from);
    if (blankIndent !== null && blankIndent <= countColumn(leadingSpace(headerLine.text), 8)) continue;
    const colon = definition.getChild('Body')?.getChild(':');
    scopes.push({
      from: name.from,
      start: headerLine.from,
      end: colon?.to ?? Math.min(headerLine.to, definition.to),
    });
  }
  return scopes;
}

export function pythonScopeLabel(doc, scope) {
  return doc.sliceString(scope.start, scope.end).split('\n').map(line => line.trim()).join(' ');
}

export const pythonScopeView = ViewPlugin.fromClass(class {
  constructor(view) {
    this.view = view;
    this.pin = document.createElement('button');
    this.pin.type = 'button';
    this.pin.className = 'python-definition-pin';
    this.pin.hidden = true;
    this.pin.onclick = () => {
      const [scope] = this.scopes;
      if (!scope) return;
      view.dispatch({selection: {anchor: scope.from}, effects: EditorView.scrollIntoView(scope.start, {y: 'start', yMargin: 16})});
      view.focus();
    };
    view.dom.append(this.pin);
    view.scrollDOM.addEventListener('scroll', this.measure, {passive: true});
    this.updateScope();
    this.measure();
  }

  update(update) {
    const scopeChanged = update.docChanged || update.selectionSet || syntaxTree(update.startState) !== syntaxTree(update.state);
    if (scopeChanged) this.updateScope();
    if (scopeChanged || update.viewportChanged || update.geometryChanged) this.measure();
  }

  updateScope() {
    const {state} = this.view;
    const previous = this.scopes?.[0], previousDoc = this.doc;
    this.doc = state.doc;
    this.scopes = pythonScopesAt(syntaxTree(state), state.doc, state.selection.main.head);
    const [scope] = this.scopes;
    if (!scope) {
      this.pin.hidden = true;
      return;
    }
    if (previousDoc === state.doc && previous?.start === scope.start && previous.end === scope.end) return;
    const label = pythonScopeLabel(state.doc, scope);
    if (this.pin.textContent !== label) {
      this.pin.textContent = label;
      this.pin.title = label;
      this.pin.setAttribute('aria-label', 'Go to current Python definition: ' + label);
    }
  }

  measure = () => {
    const [scope] = this.scopes;
    if (!scope) return;
    this.view.requestMeasure({
      key: this,
      read: view => {
        const bounds = view.scrollDOM.getBoundingClientRect();
        const bottom = view.documentTop + view.lineBlockAt(scope.end).bottom;
        return bounds.height > 0 && bottom <= bounds.top;
      },
      write: visible => {
        if (this.scopes[0] === scope) this.pin.hidden = !visible;
      }
    });
  };

  destroy() {
    this.view.scrollDOM.removeEventListener('scroll', this.measure);
    this.pin.remove();
  }
}, {
  provide: plugin => EditorView.scrollMargins.of(view => {
    const pin = view.plugin(plugin)?.pin;
    return pin && !pin.hidden ? {top: pin.offsetHeight} : null;
  })
});
