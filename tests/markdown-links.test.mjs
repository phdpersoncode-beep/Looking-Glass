import test from 'node:test';
import assert from 'node:assert/strict';
import {parser} from '@lezer/markdown';
import {Text} from '@codemirror/state';
import {markdownLinks} from '../frontend/markdown-links.mjs';

test('intervals and undefined references stay literal; explicit and defined links remain links', () => {
  const source = '[0, 1] [a,b] [unknown] [site](https://example.com) [named][id] [id] [id][]\n\n[id]: https://example.com';
  const doc = Text.of(source.split('\n'));
  assert.deepEqual([...markdownLinks(parser.parse(source), doc)],
    ['[site]', '[named]', '[id] [id][]', '[id][]'].map(text => source.indexOf(text)));
});

test('reference labels ignore case and repeated whitespace; code does not define links', () => {
  const source = '[Some   Label] [fake]\n\n[some label]: /page\n\n```\n[fake]: /no\n```';
  assert.deepEqual([...markdownLinks(parser.parse(source), Text.of(source.split('\n')))], [0]);
});
