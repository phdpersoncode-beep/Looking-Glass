"""Disposable HTTP benchmark; never touches a user's workspace."""
import json
import statistics
import tempfile
import time
from pathlib import Path
from looking_glass.app import create_app

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);app=create_app(root);ws=app.extensions['workspace']
    content='A passage for review.\n'+'text '*13000
    with ws.connection() as db:
        for i in range(100):
            name=f'{i:03}.txt';(root/name).write_text(content)
            db.execute('INSERT INTO snapshots VALUES(?,?)',(name,content))
            for j in range(10):
                identifier=db.execute('INSERT INTO threads(path,start,end,quote) VALUES(?,0,9,?)',(name,content[:9])).lastrowid
                db.execute('INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)',(identifier,'Tester','Review this passage.'))
    c=app.test_client();headers={'X-Looking-Glass-Token':ws.token}
    original=ws.text;reads=[0]
    def counted(path):
        reads[0]+=1
        return original(path)
    ws.text=counted
    def measure(routes,extra=None):
        elapsed=[];counts=[];sizes=[]
        for _ in range(5):
            reads[0]=0;start=time.perf_counter();responses=[c.get(route,headers={**headers,**(extra or {})}) for route in routes]
            assert all(r.status_code in (200,304) for r in responses)
            elapsed.append(1000*(time.perf_counter()-start));counts.append(reads[0]);sizes.append(sum(len(r.data) for r in responses))
        return {'median_ms':round(statistics.median(elapsed),2),'cold_ms':round(elapsed[0],2),'source_reads':counts[-1],'response_bytes':sizes[-1]}
    result={'files':100,'threads':1000,'legacy_refresh':measure(['/api/threads','/fragments/threads?scope=all'])}
    if any(rule.rule=='/api/discussions' for rule in app.url_map.iter_rules()):
        result['discussion_refresh']=measure(['/api/discussions?scope=all'])
        result['navigation_index']=measure(['/api/thread-index'])
        tag=c.get('/api/discussions?scope=all',headers=headers).headers['ETag']
        result['unchanged_refresh']=measure(['/api/discussions?scope=all'],{'If-None-Match':tag})
    print(json.dumps(result,indent=2))
