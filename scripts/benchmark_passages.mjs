// Dense source projection only: this does not measure DOM/editor rendering.
import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
import {sourceSpans} from '../frontend/passages.mjs';

const line = 'Line 😀 café\r\n', targetBytes = 200 * 1024;
const text = line.repeat(Math.ceil(targetBytes / Buffer.byteLength(line)));
const points = Array.from(text), count = 300, path = 'benchmark.txt';
const threads = Array.from({length: count}, (_, index) => {
  const start = Math.floor((index + 1) * points.length / (count + 1));
  return {id: index + 1, path, anchor_kind: 'source', anchor_status: 'attached',
    start, end: start + 8, quote: points.slice(start, start + 8).join(''), resolved: false};
});

// Exact projection algorithm from the starting commit, 582c3b6.
const toUnits = (source, offset) => Array.from(source).slice(0, offset).join('').replace(/\r\n/g, '\n').length;
const baseline = () => threads.map(thread => ({id: thread.id, resolved: thread.resolved,
  from: toUnits(text, thread.start), to: toUnits(text, thread.end)})).filter(span => span.from < span.to && span.to <= text.length);
const batched = () => sourceSpans(threads, text, path, 'benchmark');
assert.deepEqual(batched(), baseline());

function measure(project) {
  const samples = [];
  for (let run = 0; run < 3; run++) {
    const start = performance.now(); project(); samples.push(performance.now() - start);
  }
  return Math.round(samples.sort((a, b) => a - b)[1] * 100) / 100;
}
console.log(JSON.stringify({node: process.version, source_bytes: Buffer.byteLength(text),
  threads: count, samples: 3, median_baseline_ms: measure(baseline),
  median_batched_ms: measure(batched), equivalent_ranges: true}, null, 2));
