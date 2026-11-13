# Statement analytics on small hosts

The query analytics endpoint aggregates cumulative statement snapshots in SQL.
It transfers query summaries and collection intervals instead of complete raw
snapshots and their JSON payloads. `limit` applies to the query list; the timeline
and totals still describe all matching queries.

`statement_aggregation.py` bounds the window to the requested time range,
partitions counters by query ID, database role and execution level, and rejects
deltas across resets, evictions or decreasing counters. The first observation in
the range establishes a baseline rather than inventing executions. Actual
collection interval boundaries and zero-call intervals remain visible.

The SQL window materializes a narrow projection of counters and the typed
`stats_since` timestamp. Summaries group by query ID, role and the shared SQL
text reference before fetching representative SQL. Large SQL is not transferred
per snapshot. Search and exclusion still use Python normalization, then select
matching text references for the timeline.

## Deployment

Apply `20261112_02_typed-statements` before deploying the updated API.
It supersedes the initial JSON reset-marker optimization and removes the
serialized payload, auxiliary marker and repeated SQL text from snapshots.
See [structured statement storage](statement-storage.md) for the coordinated
PostgreSQL/SQLite upgrade, transport compatibility and rollback requirements.
Run `ANALYZE metric.query_workload` after conversion.

The additional window index can be created concurrently before the migration on
an existing busy database:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS query_workload_window_idx
ON metric.query_workload(database_id, query_id, user_id, is_toplevel, collected_at);
```

The migration detects this existing index. It does not raise `work_mem` or
`shared_buffers`. Large windows can still spill compact records to disk; measure
query latency, temporary I/O, ingestion delay and available host RAM together.

## Regression checks

The PostgreSQL equivalence tests use a dedicated temporary database and compare
the compact response against the original snapshot computation:

```powershell
$env:PGWARDEN_ANALYTICS_TEST_DSN='host=127.0.0.1 port=55439 user=postgres dbname=postgres'
cd api
.venv/Scripts/python.exe -m pytest tests/unit --confcutdir=tests/unit -q
```

The connection must point to a development server where creating and dropping a
temporary database is permitted. No application database is used for fixtures.

## Initial production validation (2026-11-12)

On the shared 3.3 GiB monitoring host, the original endpoint exceeded a 60-second
HTTP timeout and left database work running after the client disconnected.
The retained dataset contained approximately 447,000 statement snapshots,
374 query identities and 1,284 collection intervals. A one-week preset covered
the available history, not seven full days of observations.

With `shared_buffers=128MB` and `work_mem=4MB` unchanged, the optimized endpoint
returned HTTP 200 in 26.9 seconds for one day, 25.5 seconds for the one-week
preset, and 50.0 seconds with `search=select`, while ingestion continued.
Periodic samples recorded approximately 226–242 MiB for the two-worker API,
271–289 MiB for PostgreSQL and at least 1,476 MiB available on the host.
These are initial observations, not memory limits or load-test guarantees.
The final image's follow-up HTTP check completed the one-day query in 25.1
seconds, with API samples around 217 MiB, database samples at 238–244 MiB and
at least 1,516 MiB available on the host. Ingestion continued returning HTTP 200.

Filtered requests compute a second narrow window after Python resolves
normalized text matches. History and context read typed snapshots and the
referenced SQL text; they no longer parse stored JSON.

## Typed-storage follow-up

After migrating 522,558 snapshots into typed columns and 381 shared SQL texts,
the same small PostgreSQL profile remained active. With collection and delivery
running, HTTP checks completed in 5.6 seconds for a one-day query, 3.7 seconds
for the one-week preset and 6.1 seconds for `search=select`. The retained history
was approximately 26 hours, so the weekly preset still did not represent a full
seven days of data. History and context checks completed in 75 ms and 668 ms.

The periodic samples during those requests recorded approximately 239–246 MiB
for the API, 281–283 MiB for PostgreSQL and at least 1,454 MiB available on the
host. The converted PostgreSQL sample table and indexes occupied approximately
342 MiB, and the shared text table about 560 KiB. The SQLite collector file was
compacted from 3,905,568,768 bytes to 256,061,440 bytes after checking all snapshot
counts, outbox contents, source identity, foreign keys and database integrity.
Compressed pre-migration backups remain separate from these database-file sizes.
