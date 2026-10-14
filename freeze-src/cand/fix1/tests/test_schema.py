"""Record-schema test: every ON-path record carries the required keys/types."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix1_common import close, di, fresh_service, ingest_all
import canary


def main():
    tmp = tempfile.mkdtemp(prefix='fix1-schema-')
    out = Path(tempfile.mkdtemp(prefix='fix1-schema-out-'))
    tl, service = fresh_service(tmp)
    try:
        docs = ingest_all(service)
        rec = di.DrainRecorder(out, enabled=True)

        def await_pub():
            service.last_future.result()

        idx = 0
        while service.pending():
            rep = di.drain_one_cycle(service, tl, 'schema_drain', idx, rec,
                                     await_pub,
                                     max_documents=canary.CYCLE_DOCS)
            assert not rep['failed'] and rep['attempted']
            idx += 1
        rows = di.read_records(rec.path)
        assert len(rows) == 3, len(rows)
        for lineno, record in rows:
            missing = [k for k in di.CYCLE_KEYS if k not in record]
            assert not missing, (lineno, missing)
            assert record['type'] == 'cycle'
            assert isinstance(record['wall_s'], float) and record['wall_s'] > 0
            assert isinstance(record['lock_hold_s'], float)
            assert isinstance(record['attempted_docs'], int)
            assert isinstance(record['committed_docs'], int)
            assert isinstance(record['commits_after'], int), record
            split = record['prepare_split']
            for k in ('viewpool_build_s', 'source_verify_s', 'scan_s', 'note'):
                assert k in split, (lineno, k)
        attempted = sum(r['attempted_docs'] for _, r in rows)
        assert attempted == len(docs), (attempted, len(docs))
        print('schema: %d cycle records, all keys/types ok, attempted=%d'
              % (len(rows), attempted))
    finally:
        close(service, tl)
    print('PASS test_schema')
    return 0


if __name__ == '__main__':
    sys.exit(main())
