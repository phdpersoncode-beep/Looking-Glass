import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fuzzyCard,cardReference} from '../frontend/tasks.mjs';
test('card search matches subsequences in title and description safely',()=>{
 const card={title:'Release planning',description:'Unicode café <script>'};
 assert.equal(fuzzyCard(card,'rlsp'),true);
 assert.equal(fuzzyCard(card,'CAFÉ'),true);
 assert.equal(fuzzyCard(card,'xyz'),false);
 assert.equal(fuzzyCard(card,''),true);
});

test('stable card references work in exact search',()=>{
 assert.equal(cardReference(1),'#C01');
 assert.equal(cardReference(123),'#C123');
 assert.equal(fuzzyCard({id:12,title:'Plan',description:''},'#C12'),true);
 assert.equal(fuzzyCard({id:12,title:'Plan',description:''},'C012'),true);
 assert.equal(fuzzyCard({id:12,title:'Plan',description:''},'#C1'),false);
});
