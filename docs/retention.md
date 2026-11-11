# Scoped metric retention

Settings → Retention supports a global default, project policies and server policies.
The effective rule is resolved in this order:

1. Server rule for the metric table.
2. Server rule for all tables.
3. Project rule for the metric table.
4. Project rule for all tables.
5. Global rule for the metric table.
6. Global rule for all tables.

No matching rule means no automatic deletion. A server without a project inherits
the global defaults. **Use inherited policy** removes the selected override.
Changing an all-table default preserves table-specific rules within that scope
and all rules in more specific scopes. The existing global replication action
updates global table defaults together, preserving project/server overrides.

## Deployment and cleanup

Apply `20261104_01_scoped-retention` through the normal migration service before
deploying the updated API. It copies native metric retention durations and paused
states into `retention.policy`, backs them up in `retention.native_backup`, and
removes native retention jobs. Mixed calendar intervals and policies based on
chunk creation time require conversion before migration; the migration fails
atomically instead of guessing their meaning.

Do not run an older API version alongside the new API: it can recreate unsafe
native retention jobs. Stop old API instances during deployment, run migrations,
and start only the updated API instances.

The API lifespan starts the retention worker. Each pass visits every existing
server and allowlisted metric table and deletes at most 1,000 expired rows per
combination, committing each batch independently. Passes run one minute apart;
a large backlog can require several passes. Every batch resolves the current
policy again. A database advisory lock coordinates policy changes and concurrent
API workers. Server ownership is locked for the batch. Cleanup retains rows at
the exact cutoff and ignores paused rules. Soft-deleted servers continue to be
cleaned. Moving a server to another project changes the rule for all its history.

Cleanup supports `metric.column`, `cpu`, `database_stat`, `disk`, `index`, `io`,
`lock`, `native_query`, `query_workload`, `ram`, `session` and `table`. New supported
tables inherit all-table rules automatically; new metric types must be added to
the ownership registry. Every cleanup table must have a primary key.

Native chunk retention must stay disabled because chunks can contain multiple
servers with different deadlines. Cleanup fails closed and logs an error if a
native metric retention job is recreated. The UI exposes the last successful
batch and removed-row count per server/table in the effective-policy table.
Failed batches roll back and are retried on later passes; inspect API logs when
cleanup history stops advancing.

Row deletion works with TimescaleDB's supported compressed DML (2.11+ on
PostgreSQL 14+). It can require selective decompression and is more expensive
than dropping chunks. The application's current TimescaleDB configuration
already uses newer columnstore features.

## Estimates

Scoped estimates count affected rows and sum `pg_column_size` within the chosen
scope, preserving more specific overrides and paused rules. Projections use the
observed logical bytes per elapsed time. These are logical row-volume estimates,
not physical disk forecasts: they exclude indexes, compression and free pages.
Deleting rows makes space reusable and does not guarantee immediate filesystem
shrinkage. The estimate itself never deletes data.

## Tests

Unit tests:

```powershell
cd api
.venv/Scripts/python.exe -m pytest tests/retention --confcutdir=tests/retention -q
```

Actual PostgreSQL deletion tests create a randomly named disposable database and
drop only that database at completion. The configured administrative connection
must be a test server with database-creation permission:

```powershell
cd api
$env:RETENTION_TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:55439/postgres'
.venv/Scripts/python.exe -m pytest tests/retention_scoped --confcutdir=tests/retention_scoped -q
```

The suite applies the actual metric migrations, checks retained rows across all
12 metric tables, runs the production cleanup pass, exercises HTTP permissions,
and verifies inheritance, boundary handling, rollback and coordination locks.
Set `RETENTION_TIMESCALE_TEST_DATABASE_URL` to a TimescaleDB test server to also
execute native-policy migration and compressed-table isolation checks. That test
is skipped when the extension is unavailable; ordinary PostgreSQL tests do not
claim to validate TimescaleDB compression.

Frontend validation uses `npm test`, `npm run check` and `npm run build` in
`frontend`.
