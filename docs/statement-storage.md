# Structured statement snapshots

`metric.query_workload` stores typed `pg_stat_statements` columns. SQL text is
stored once per monitored database and SHA-256 fingerprint in
`metric.statement_text`; samples reference it through `statement_text_id`.
Different roles and execution levels retain independent counter histories even
when their SQL text is shared.

The schema covers the PostgreSQL 14–18 extension fields: planning/execution
counts and timings, returned rows, shared/local/temp blocks and I/O timings,
WAL counters, JIT counters/timings, parallel workers and reset timestamps.
Fields absent from the monitored extension version remain SQL NULL. The source
database OID is kept separately from PGWarden's mapped database identity.
`wal_bytes` uses PostgreSQL `NUMERIC(30,0)` and SQLite decimal text to avoid loss
when a counter exceeds a signed 64-bit integer.

The collector reads structured extension rows without `row_to_json`. Unsupported
new fields are rejected explicitly so they can receive a reviewed schema update.
The authoritative field list is mirrored in the independently deployed services
and checked for equality in tests. See the official
[pg_stat_statements field definitions](https://www.postgresql.org/docs/18/pgstatstatements.html).

## Transport and response compatibility

The HTTP ingestion envelope and SQLite outbox remain JSON transport formats.
The sender expands the local text reference into `query` and `query_hash` while
capturing an immutable event; local dictionary IDs never cross projects or
collectors. The receiver resolves a central, database-scoped text reference.
Queued version-1 events containing legacy `statement_data` are converted and
validated before insertion. Legacy payloads cannot override identity or the
existing core counters. Unknown fields cause rejection rather than silent loss.

Ingestion receipts retain event IDs and the fingerprint of the original envelope
for deduplication. For statement samples their payload is `{}`; the full sample
is not duplicated indefinitely. `migrations/prune_statement_receipts.py` clears
older copies in committed batches without deleting replay receipts.

History and context keep the existing `statement_data` response object for the
frontend. It is assembled from typed columns when requested; it is not a stored
JSON column. Numeric values that need exact decimal serialization use strings.

## Upgrade order

1. Back up PostgreSQL and the complete SQLite database, including outbox and
   sender state. Preserve encryption keys and ingestion fingerprints.
2. Pause the collector, sender, API and analytics workers for the schema switch.
3. Apply `20261112_02_typed-statements` in the central PostgreSQL and collector
   SQLite deployments. The migration checks field coverage and row counts,
   builds normalized replacements and removes the legacy text/JSON columns.
4. Deploy the updated receiving API and analytics service, then the collector
   and sender. Sender initialization refreshes capture triggers. It does not
   rewrite existing outbox events or rotate the source identity.
5. Verify snapshot counts, dictionary counts, newest collection times, replay
   handling and ingestion before pruning old receipt payloads. Run `ANALYZE`
   after conversion and measure RAM and latency under the existing small profile.

The SQLite migration avoids sorting full SQL texts to build its dictionary and
disables secure-delete writes for the conversion. Check disk headroom, checkpoint
the WAL and use rollback-journal mode while writers are paused. Normal sender
startup restores WAL. Free pages are reusable; compact with `VACUUM` only when
there is enough temporary disk space for the remaining live database.

On Docker's default 64 MiB `/dev/shm`, a parallel manual VACUUM can exceed the
shared-memory segment limit even when host RAM and disk are available. The
production follow-up used ordinary `VACUUM (ANALYZE, PARALLEL 0)` with a
connection-local 32 MiB maintenance budget; the global small-host settings were
kept unchanged.

The SQL rollback reconstructs legacy snapshots from typed columns, preserving
available statistics and text. Coordinate rollback before restarting writers:
old receivers cannot accept the new typed event fields. Once typed events are
queued, preserve their IDs and fingerprints and retain a compatible receiver
until delivery is complete. Never rewrite queued event bodies in place.
