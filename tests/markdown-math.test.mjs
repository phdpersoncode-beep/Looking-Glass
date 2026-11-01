import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import katex from 'katex';
import {markdown,readMath,mathOptions} from '../frontend/markdown-math.mjs';
import {markdownMathRanges,mappedMarkdownHTML} from '../frontend/markdown-source.mjs';

const sample=readFileSync(new URL('./fixtures/markdown-math.md',import.meta.url),'utf8');
const slotsFor=(source,offset=0)=>{const slots=[];mappedMarkdownHTML(source,offset,slots);return slots;};

test('the requested cases, operators, table parameters and concatenation are complete math tokens',()=>{
  const slots=slotsFor(sample);
  assert.equal(slots.length,8);assert.equal(slots.filter(s=>s.display).length,2);
  assert.deepEqual(slots.slice(4,7).map(s=>s.text),['R','B','K']);
  for(const slot of slots){
    assert.equal(sample.slice(slot.position.from,slot.position.to),slot.raw);
    const html=katex.renderToString(slot.text,{...mathOptions,displayMode:slot.display});
    assert.match(html,/<math /);assert.match(html,/encoding="application\/x-tex"/);
    assert.doesNotMatch(html,/katex-error/);
  }
  assert.match(katex.renderToString(slots[0].text,mathOptions),/mfrac/);
});

test('dollar and TeX delimiters, single-line displays and math fences preserve source ranges',()=>{
  const source=String.raw`Inline $x_i^2$ and \(\alpha+\beta\).`+'\n\n$$x=y$$\n\n'+String.raw`\[
\begin{aligned}a&=b\\c&=d\end{aligned}
\]`+'\n\n```latex\n\\sqrt{x}\n```\n\n~~~tex\n\\pi\n~~~\n\n```math\nx_1\n```\n';
  const slots=slotsFor(source);
  assert.equal(slots.length,7);
  assert.deepEqual(slots.map(s=>s.display),[false,false,true,true,true,true,true]);
  for(const slot of slots)assert.equal(source.slice(slot.position.from,slot.position.to),slot.raw);
  assert.deepEqual(markdownMathRanges(source).map(({from,to})=>source.slice(from,to)),slots.map(s=>s.raw));
});

test('core LaTeX constructs produce MathML without errors',()=>{
  for(const text of [
    String.raw`\frac{a}{b}+\dfrac{1}{2}+\sqrt[3]{x}`,String.raw`\sum_{i=1}^{n}i^2+\prod_{j=1}^{m}j`,
    String.raw`\int_0^\infty e^{-x}\,dx=1`,String.raw`\lim_{x\to0}\frac{\sin x}{x}=1`,
    String.raw`\begin{pmatrix}a&b\\c&d\end{pmatrix}`,String.raw`\begin{bmatrix}1&0\\0&1\end{bmatrix}`,
    String.raw`\left\lVert\vec{x}\right\rVert\leq\infty`,String.raw`\hat{x}+\bar{y}+\overbrace{a+b}^{n}`,
    String.raw`\mathbb{R}\subseteq\mathcal{P}(X),\quad A\cap B\ne\varnothing`,
    String.raw`\underbrace{x+\cdots+x}_{n}\xrightarrow{n\to\infty}\infty`,
    String.raw`\newcommand{\pair}[2]{\langle #1,#2\rangle}\pair{x}{y}`,String.raw`\text{with spaces}\quad\operatorname{Vol}(M)`
  ])assert.match(katex.renderToString(text,{...mathOptions,displayMode:true}),/katex-mathml/);
});

test('escaped dollars, prices, code, URLs and unmatched delimiters remain ordinary Markdown',()=>{
  const source=String.raw`Costs $5 and $10; escaped \$x\$; $ unclosed; \(unfinished; [link](https://example.test/$x$).

\`$code$\`

~~~python
value = "$literal$"
~~~

    $indented$
`.replaceAll('\\`','`');
  assert.equal(slotsFor(source).length,0);
  assert.match(markdown.parse(source),/language-python/);
  for(const input of ['$ x$','$x $','$x\ny$','$$unfinished',String.raw`\[unfinished`])assert.equal(readMath(input),null);
  assert.equal(readMath(String.raw`$a\$b$`).text,String.raw`a\$b`);
});

test('Unicode, CRLF, repeated formulas, quotes, lists and escaped table pipes keep exact coordinates',()=>{
  const source='😀 **before**\r\n\r\n> $x$ and $x$\r\n\r\n- $y$\r\n\r\n| Math |\r\n|---|\r\n| $a\\|b$ |\r\n\r\n$$\r\na+b\r\n$$\r\n';
  const slots=slotsFor(source,37);
  assert.equal(slots.length,5);
  for(const slot of slots){
    const raw=source.slice(slot.position.from-37,slot.position.to-37);
    assert.equal(raw.replaceAll('\r\n','\n').replaceAll('\\|','|'),slot.raw);
  }
  assert.deepEqual(slots.slice(0,2).map(s=>s.position.from-37),[source.indexOf('$x$'),source.lastIndexOf('$x$')]);
});

test('untrusted commands stay inert and macro state is local to one formula',()=>{
  for(const text of [String.raw`\href{javascript:alert(1)}{click}`,String.raw`\includegraphics{https://example.test/track}`,String.raw`\htmlClass{thread-action}{x}`]){
    const html=katex.renderToString(text,mathOptions);
    assert.doesNotMatch(html,/<a\b|<img\b|class="thread-action"|href="javascript:/);
  }
  assert.match(katex.renderToString(String.raw`\gdef\local{x}\local`,mathOptions),/katex/);
  assert.throws(()=>katex.renderToString(String.raw`\local`,mathOptions));
  assert.throws(()=>katex.renderToString(String.raw`\def\loop{\loop}\loop`,mathOptions),/Too many expansions/);
});

test('adjacent inline formulas keep separate source passages',()=>{
  assert.deepEqual(slotsFor('$x$$y$').map(s=>({raw:s.raw,position:s.position})),[
    {raw:'$x$',position:{from:0,to:3}},{raw:'$y$',position:{from:3,to:6}}
  ]);
});
