// Run from the repository root: node scripts/benchmark_thread_search.mjs [count]
// Measures the local search engine, excluding sidebar rendering/network time.
import {createThreadSearch} from '../frontend/thread-search.mjs';
const count=Number(process.argv[2]||3000);
const threads=Array.from({length:count},(_,i)=>({id:i+1,quote:`Parameter configuration for the CAD model ${i}`,messages:[
  {body:'Review the geometry verifier and topology constraints. '.repeat(6)},
  {body:'Validate dimensions before running another search.'},
]}));
let start=performance.now();const search=createThreadSearch(threads);
console.log(`Index ${count} threads: ${(performance.now()-start).toFixed(1)} ms`);
for(const query of ['geometry','geomtery','#129','topology dimensions','absent']){
  start=performance.now();const results=search(query);
  console.log(`${query}: ${results.length} matches, ${(performance.now()-start).toFixed(1)} ms`);
}
