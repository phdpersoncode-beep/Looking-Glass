import test from 'node:test';
import assert from 'node:assert/strict';
import {createDiscussionRetention} from '../frontend/discussion-lifetime.mjs';

test('hidden review discussions remain retained across ordinary visibility', () => {
  const retention = createDiscussionRetention();
  retention.accept('ordinary', [1]);
  retention.accept('pending-reviews', [1, 2]);
  assert.deepEqual([...retention.accept('ordinary', [1])], [1, 2]);
  assert.deepEqual([...retention.accept('pending-reviews', [1, 2])], [1, 2]);
});

test('observed deletion retires an ID in every cached scope', () => {
  const retention = createDiscussionRetention();
  retention.accept('ordinary', [1, 2]);
  retention.accept('pending-reviews', [1, 2, 3]);
  assert.deepEqual([...retention.accept('ordinary', [2])], [2, 3]);
  assert.deepEqual([...retention.accept('pending-reviews', [2])], [2]);
});
