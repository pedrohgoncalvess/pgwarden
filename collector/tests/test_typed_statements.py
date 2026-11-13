"""Verify SQLite upgrades preserve history and immutable queued events."""

import json
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from sender import initialize

ROOT = Path(__file__).resolve().parents[2]


def test_sqlite_upgrade_preserves_queue_precision_and_shared_text():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    for migration in sorted((ROOT/'migrations/sqlite').glob('*.sql')):
        if not migration.name.endswith('.rollback.sql') and migration.name < '20261112_02':
            db.executescript(migration.read_text())
    db.execute("INSERT INTO collector_server(name,host,port,username,password) VALUES('a','h','p','u','s')")
    db.execute("INSERT INTO metadata_database(server_id,db_name) VALUES(1,'app')")
    db.commit()
    cipher = Fernet(Fernet.generate_key())
    initialize(db,'http://localhost/events','pgw_initial',cipher)
    source = db.execute('SELECT source_id FROM sender_state').fetchone()[0]
    for minute in (0,1):
        db.execute('''INSERT INTO metric_query_workload
            (collected_at,database_id,query_id,user_id,is_toplevel,calls,total_exec_time,
             shared_blks_read,shared_blks_hit,dealloc,query,query_hash,statement_data)
            VALUES(?,1,123,10,1,10,30.5,1,2,0,'SELECT $1','legacy',?)''',
            (f'2026-11-12T10:0{minute}:00Z',
             '{"wal_bytes":18446744073709551615,"rows":7,"stats_since":"2026-11-12T00:00:00Z"}'))
    db.commit()
    pending = [tuple(row) for row in db.execute('SELECT * FROM sender_outbox ORDER BY seq')]
    db.executescript((ROOT/'migrations/sqlite/20261112_02_typed-statements.sql').read_text())
    assert [tuple(row) for row in db.execute('SELECT * FROM sender_outbox ORDER BY seq')] == pending
    initialize(db,'http://localhost/events','pgw_initial',cipher)
    assert db.execute('SELECT source_id FROM sender_state').fetchone()[0] == source
    assert db.execute('SELECT count(*) FROM metric_statement_text').fetchone()[0] == 1
    rows = list(db.execute('SELECT * FROM metric_query_workload ORDER BY collected_at'))
    assert len(rows) == 2 and rows[0]['wal_bytes'] == '18446744073709551615'
    assert rows[0]['total_exec_time'] == 30.5
    db.execute('''INSERT INTO metric_query_workload
        (collected_at,database_id,query_id,user_id,is_toplevel,calls,total_exec_time,
         shared_blks_read,shared_blks_hit,dealloc,statement_text_id,wal_bytes)
        VALUES('2026-11-12T10:02:00Z',1,123,10,1,20,40,2,3,0,1,'18446744073709551615')''')
    captured = json.loads(db.execute("SELECT data FROM sender_outbox WHERE table_name='metric_query_workload' ORDER BY seq DESC LIMIT 1").fetchone()[0])
    assert captured['query'] == 'SELECT $1'
    assert captured['wal_bytes'] == '18446744073709551615'
    assert 'statement_data' not in captured and 'statement_text_id' not in captured
    db.commit()
    db.executescript((ROOT/'migrations/sqlite/20261112_02_typed-statements.rollback.sql').read_text())
    assert db.execute('SELECT count(*) FROM metric_query_workload').fetchone()[0] == 3
    payload = json.loads(db.execute('SELECT statement_data FROM metric_query_workload ORDER BY collected_at LIMIT 1').fetchone()[0])
    assert payload['wal_bytes'] == '18446744073709551615'
    db.executescript((ROOT/'migrations/sqlite/20261112_02_typed-statements.sql').read_text())
    assert db.execute('SELECT count(*) FROM metric_query_workload').fetchone()[0] == 3
    db.close()
