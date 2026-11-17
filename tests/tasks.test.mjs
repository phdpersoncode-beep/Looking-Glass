import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fuzzyCard} from '../frontend/tasks.mjs';
test('card search matches subsequences in title and description safely',()=>{
 const card={title:'Release planning',description:'Unicode café <script>'};
 assert.equal(fuzzyCard(card,'rlsp'),true);
 assert.equal(fuzzyCard(card,'CAFÉ'),true);
 assert.equal(fuzzyCard(card,'xyz'),false);
 assert.equal(fuzzyCard(card,''),true);
});
