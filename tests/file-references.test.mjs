import test from 'node:test';
import assert from 'node:assert/strict';
import {fileReferences} from '../frontend/file-references.mjs';
import {fuzzyScore} from '../frontend/file-search.mjs';
test('file references retain punctuation, quoted spaces, Unicode, and safe workspace paths',()=>{
  assert.deepEqual(fileReferences('Read @src/part.py, and @"notes/über view.md". mail a@b.com @../secret @/etc/passwd').map(r=>r.path),['src/part.py','notes/über view.md']);
  assert.ok(fuzzyScore('src/part.py','spp')!==null);
  assert.equal(fuzzyScore('readme.md','xyz'),null);
});
