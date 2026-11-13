# Projects and remote event ingestion

Apply the PostgreSQL Yoyo migrations before upgrading the API and collector.
Administrators can open **Settings → Projects** to create a project and obtain
its initial key, change its policies, rotate keys, or revoke them. Keys permit
ingestion only; administration continues to require an administrator JWT.

Expiration and automatic rotation are independently optional. `key_expiration_days`
sets a new key's lifetime; omitting it produces a non-expiring key.
`rotation_interval_days` enables automatic replacement, checked approximately once
per minute by API workers using PostgreSQL row locks. Leave it empty for manual
rotation. If both policies are set, rotation must precede expiration. Updating a
lifetime policy affects newly issued keys, not a key already in use.

Automatic rotation uses `rotation_grace_hours` (default 24, maximum 168). During
that overlap, an accepted old key receives `replacement_key` in successful
ingestion responses, including retry responses. The sender **must persist that
replacement credential atomically before acknowledging/deleting local records**.
After overlap or expiration, the old key receives 401; an administrator must issue
a fresh key if an offline sender missed the handoff. Revoking the current key
stops scheduled rotation until an administrator issues another key. A manual
rotation defaults to zero overlap and immediately revokes every previous key.

Only key hashes and prefixes are exposed through key-list responses. Automatic
handoff temporarily retains the successor encrypted with `ENCRYPTION_KEY` so a
lost response can be retried. The rotation worker removes this encrypted copy
after no previous key remains eligible for handoff. Protect and retain that
server encryption key. Use HTTPS and keep credentials in the Authorization
header, never in a URL or event payload.

The standalone sender should call the main API:

```http
POST /v1/ingestion/events
Authorization: Bearer pgw_your_project_key
Content-Type: application/json
```

The frontend also proxies `/api/v1/ingestion/events`; configure proxy body limits
when using it. The API accepts at most 500 events and 2 MiB per request:

```json
{
  "version": 1,
  "source_id": "31d47764-9a83-4a8a-8fe6-220ef3046092",
  "events": [
    {
      "event_id": "72cd642a-a0d3-439c-8fba-b42a25ab6a6f",
      "occurred_at": "2026-10-30T12:00:00Z",
      "table": "collector_server",
      "local_id": 1,
      "data": { "name": "production-postgres" }
    },
    {
      "event_id": "9f15e455-2fa5-48c8-98ac-f730c2670054",
      "occurred_at": "2026-10-30T12:00:01Z",
      "table": "metric_cpu",
      "data": {
        "server_id": 1,
        "collected_at": "2026-10-30T12:00:01Z",
        "cpu_percent": 42.5,
        "cpu_count": 4
      }
    }
  ]
}
```

Persist a stable `source_id` for each SQLite installation. Persist each event UUID
and its immutable snapshot before sending; use the same content and ID on retry.
A new snapshot needs a new event ID. The authenticated key determines the project;
clients cannot supply a central project or entity ID. All row references use
SQLite local IDs, mapped by `(project, source, table, local_id)` on the server.

Send parent entities before dependent rows, including across batches:
`collector_server`, `metadata_database`, `metadata_table`, `metadata_column`,
`metadata_index`, then `metadata_index_column` and the relevant `metric_*` rows.
All eleven collector metric tables are accepted. An entity event needs `local_id`;
metrics and index-column relationships do not. Use timezone-aware ISO timestamps.
`occurred_at` orders entity snapshots, so older snapshots cannot overwrite newer
ones. Keep index-column relationship changes in chronological order.

`data` contains destination row fields, excluding `id`, `public_id`, actor IDs,
and ingestion-internal fields. A server accepts only `name`, `last_seen_at`,
`last_error`, `created_at`, `updated_at`, and `deleted_at`: **never send database
connection credentials**. Other entity and metric fields follow the collector's
table columns. Control tables, local run logs, and local schema-history tables
are not ingestible. Central metadata changes generate central schema history.
Soft deletion uses `deleted_at`; physical `operation: "delete"` is supported only
for index-column relationships, with its index/column IDs and ordinal position.

The API writes the event receipt, ID mappings, metadata, and metrics in one
transaction. A successful response includes `accepted`, `duplicates`,
`acknowledged_event_ids`, and an optional `replacement_key`. Remove only acknowledged
local events. Missing parents or an event ID reused with different content return
409; invalid rows return 422; oversized batches return 413. These failures roll
back the entire batch, so retain it and correct/retry delivery. Keep receipt data
while senders may retry; no automatic receipt retention is enabled yet.

Statement events use typed statistics and inline SQL in the transport envelope.
The receiver resolves a database-scoped shared SQL reference; local text IDs
are never accepted. Queued legacy `statement_data` events remain supported and
are converted before storage. Statement receipts keep their original fingerprint
and an empty payload instead of duplicating the sample. See the coordinated
[structured statement upgrade](statement-storage.md) before updating collectors.

Imported servers are marked as remotely collected so the central PostgreSQL
collector does not poll them or record the central host's system metrics against
them. Their normalized metrics are available through the existing API and UI.

Run the dedicated backend integration tests against a disposable PostgreSQL
connection by setting `INGESTION_TEST_DATABASE_URL` and running
`pytest tests/test_ingestion.py` from `api/`. They create their own database and
verify migration application/rollback, actual metric writes, isolation,
deduplication, and key lifecycles. The test baseline omits Timescale-specific DDL;
the production stack still requires TimescaleDB.


## Related documentation

- [Deployment and configuration](../README.md#remote-collection)
- [SQLite collector and sender operations](../collector/README.MD)
