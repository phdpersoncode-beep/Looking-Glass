import assert from 'node:assert/strict';
import test from 'node:test';
import {indentLess, indentMore, insertNewlineAndIndent} from '@codemirror/commands';
import {python} from '@codemirror/lang-python';
import {EditorState} from '@codemirror/state';
import {pythonIndentation} from '../frontend/python-indentation.mjs';

function editor(source) {
  const cursor = source.indexOf('|');
  const doc = source.slice(0, cursor) + source.slice(cursor + 1);
  let state = EditorState.create({
    doc, selection: {anchor: cursor}, extensions: [python(), pythonIndentation(doc)]
  });
  return command => {
    assert.ok(command({state, dispatch: transaction => { state = transaction.state; }}));
    return state.doc.toString();
  };
}

test('Python Enter follows suites and bracketed continuations', () => {
  for (const [source, insertion] of [
    ['if ready: # start here|', '\n    '],
    ['def build(\n    name,\n):|', '\n    '],
    ['def build():\n    if ready:|', '\n        '],
    ['match value:\n    case 1:|', '\n        '],
    ['values = [|]', '\n    \n'],
    ['values = [first,|', '\n          '],
    ['values = [\n    first,\n]|', '\n'],
    ['def build():\n  return item|', '\n  '],
    ['def build():\n\tif ready:|', '\n\t\t'],
    ['label = "ends in a colon:"|', '\n'],
    ['# Example:|', '\n'],
    ['total = first + \\|', '\n    '],
    ['total = first + \\\n    second + \\|', '\n    '],
    ['total = first + \\\n    second|', '\n'],
    ['# Example \\|', '\n'],
    ['text = """example \\|\n"""', '\n'],
  ]) {
    assert.equal(editor(source)(insertNewlineAndIndent), source.replace('|', insertion), source);
  }
});

test('Python Enter carries an indented blank line forward', () => {
  assert.equal(editor('if ready:\n    run()\n  |')(insertNewlineAndIndent), 'if ready:\n    run()\n\n  ');
});

test('Python indent and outdent use the same unit as Enter', () => {
  const run = editor('if ready:|');
  assert.equal(run(insertNewlineAndIndent), 'if ready:\n    ');
  assert.equal(run(indentMore), 'if ready:\n        ');
  assert.equal(run(indentLess), 'if ready:\n    ');
});
