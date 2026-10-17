import test from 'node:test';
import assert from 'node:assert/strict';
import {highlightTree,classHighlighter} from '@lezer/highlight';
import {markdown} from '@codemirror/lang-markdown';
import {codeLanguage} from '../frontend/code-languages.mjs';

function tokens(parser,source){
  const result=[];
  highlightTree(parser.parse(source),classHighlighter,(from,to,classes)=>result.push({text:source.slice(from,to).trim(),classes}));
  return result;
}
const samples={yaml:'name: "Looking Glass"\ncount: 12\n# configuration\n',yml:'name: "Looking Glass"\ncount: 12\n# configuration\n',toml:'[project]\nname = "Looking Glass"\ncount = 12\n# configuration\n'};
for(const [name,source] of Object.entries(samples))for(const fenced of [false,true])test(`${name} highlights keys, strings, numbers and comments in ${fenced?'Markdown fences':'files'}`,()=>{
  const input=fenced?'```'+name+'\n'+source+'```\n':source;
  const parser=fenced?markdown({codeLanguages:codeLanguage}).language.parser:codeLanguage(name).parser;
  const found=tokens(parser,input);
  assert.ok(found.some(t=>t.text==='name'&&/tok-(atom|propertyName)/.test(t.classes)),JSON.stringify(found));
  assert.ok(found.some(t=>t.text==='"Looking Glass"'&&t.classes.includes('tok-string')));
  assert.ok(found.some(t=>t.text==='12'&&t.classes.includes('tok-number')));
  assert.ok(found.some(t=>t.text==='# configuration'&&t.classes.includes('tok-comment')));
});
test('language aliases, case, trailing fence metadata, and unknown languages',()=>{
  assert.equal(codeLanguage(' YAML extra '),codeLanguage('yml'));
  assert.equal(codeLanguage('TOML'),codeLanguage('toml'));
  assert.equal(codeLanguage('unknown'),null);
  for(const [alias,name] of [['py','python'],['sh','bash'],['shell','bash'],['htm','html']])assert.equal(codeLanguage(alias),codeLanguage(name));
  for(const name of ['python','bash','json','html'])assert.ok(codeLanguage(name).parser);
});
