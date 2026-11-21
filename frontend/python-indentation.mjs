import {pythonLanguage} from '@codemirror/lang-python';
import {getIndentUnit, indentService, indentUnit, syntaxTree} from '@codemirror/language';

function existingUnit(source) {
  const sample = source.slice(0, 16_384);
  const leading = position => {
    const start = sample.lastIndexOf('\n', position - 1) + 1;
    return sample.slice(start, position).match(/^[ \t]*/)[0];
  };
  let unit;
  pythonLanguage.parser.parse(sample).iterate({enter(ref) {
    if (unit) return false;
    if (ref.name !== 'Body' && ref.name !== 'MatchBody') return;
    const colon = ref.node.firstChild;
    if (colon?.name !== ':') return;
    let statement = colon.nextSibling;
    while (statement?.name === 'Comment') statement = statement.nextSibling;
    if (!statement || statement.type.isError || !sample.slice(colon.to, statement.from).includes('\n')) return;
    const parent = leading(ref.node.parent.from), child = leading(statement.from);
    if (!child.startsWith(parent)) return;
    const step = child.slice(parent.length);
    if (/^( {1,8}|\t)$/.test(step)) unit = step;
  }});
  return unit || '    ';
}

function explicitContinuation(state, line) {
  if (!line.text.endsWith('\\')) return false;
  for (let node = syntaxTree(state).resolveInner(line.to - 1, 1); node; node = node.parent) {
    if (['Comment', 'String', 'FormatString'].includes(node.name)) return false;
    if (['(', '[', '{'].includes(node.firstChild?.name)) return false;
  }
  return true;
}

function continuationIndent(context, position) {
  if (context.simulatedBreak !== position) return;
  const {state} = context, line = state.doc.lineAt(position);
  if (position !== line.to) return;
  const indent = context.lineIndent(position, -1);
  // Keep a blank line's manually chosen indentation when continuing from it.
  if (/^[ \t]+$/.test(line.text)) return indent;
  if (!explicitContinuation(state, line)) return;
  const continuing = line.number > 1 && explicitContinuation(state, state.doc.line(line.number - 1));
  return continuing ? indent : indent + getIndentUnit(state);
}

export function pythonIndentation(source) {
  return [indentUnit.of(existingUnit(source)), indentService.of(continuationIndent)];
}
