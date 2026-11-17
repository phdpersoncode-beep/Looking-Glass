import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fuzzyCard,cardReference,displayReference} from '../frontend/tasks.mjs';
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

test('milestone display and search retain a separate permanent card reference',()=>{
 const card={id:12,title:'Release',description:'',milestone:1,reference:'#M2',milestone_reference:'#M2',card_reference:'#C12'};
 assert.equal(displayReference(card),'#M2');
 assert.equal(fuzzyCard(card,'#M2'),true);
 assert.equal(fuzzyCard(card,'m02'),true);
 assert.equal(fuzzyCard(card,'#M1'),false);
 assert.equal(fuzzyCard(card,'#C12'),true);
 const demoted={...card,milestone:0,reference:'#C12',milestone_reference:null};
 assert.equal(displayReference(demoted),'#C12');
 assert.equal(fuzzyCard(demoted,'#M2'),false);
 assert.equal(fuzzyCard(demoted,'C12'),true);
});
