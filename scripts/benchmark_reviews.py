"""Disposable comparison of ordinary saves, review edits, and unchanged polls."""
import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from looking_glass.app import create_app


def measure(call):
    start=time.perf_counter(); result=call(); return result,(time.perf_counter()-start)*1000


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mib',type=int,default=1);parser.add_argument('--iterations',type=int,default=20)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);source=('value = 12345  # example\n'*((args.mib*1024*1024-args.iterations*2)//25))
        (root/'edit.py').write_text(source);(root/'review.py').write_text(source)
        app=create_app(root);ws=app.extensions['workspace'];client=app.test_client();headers={'X-Looking-Glass-Token':ws.token}
        ordinary=ws.read('edit.py');file=ws.read('review.py');draft=ws.reviews.start(file['path'],file['version'])
        save_times=[];review_times=[];poll_times=[];reply_bytes=[]
        for i in range(args.iterations):
            ordinary,t=measure(lambda:ws.save(ordinary['path'],ordinary['content']+'x',ordinary['version']));save_times.append(t)
            response,t=measure(lambda:client.patch(f'/api/reviews/{draft["id"]}',headers=headers,json=dict(version=draft['version'],author='Altay',role='human',minimal=True,operations=[dict(start=len(source)+i,end=len(source)+i,insert='x')])));review_times.append(t)
            assert response.status_code==200;draft.update(response.json);reply_bytes.append(len(response.data))
            response,t=measure(lambda:client.get(f'/api/reviews/{draft["id"]}?version='+draft['version'],headers=headers));poll_times.append(t)
            assert response.status_code==304
        assert (root/'review.py').read_text()==source
        print(json.dumps(dict(source_bytes=len(source.encode()),iterations=args.iterations,
            median_edit_save_ms=round(statistics.median(save_times),2),median_review_edit_ms=round(statistics.median(review_times),2),
            median_unchanged_review_poll_ms=round(statistics.median(poll_times),2),max_human_acknowledgement_bytes=max(reply_bytes),
            original_preserved=True),indent=2))


if __name__=='__main__':main()
