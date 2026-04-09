import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { authSelectors, useAuthStore } from "@/modules/auth/auth.store";
import { dashboardQueries } from "@/modules/dashboard/dashboard.queries";
import { PerformanceChart } from "@/modules/dashboard/dashboard.performance-chart";
import { formatApiError, statusBadgeClass } from "@/modules/dashboard/dashboard.ui";
import { SetupEmptyState } from "@/modules/dashboard/setup/setup.empty-state";

export function DashboardPage() {
  const accessToken = useAuthStore(authSelectors.accessToken);
  const navigate = useNavigate();
  const search = useSearch({ from: "/" });
  const selectedServerId = search.serverId ?? null;
  const selectedDatabaseId = search.dbId ?? null;
  const [tableSearch, setTableSearch] = useState("");
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);

  const serversQuery = useQuery({
    ...dashboardQueries.servers(accessToken),
    refetchInterval: 5_000,
  });
  const databasesQuery = useQuery({
    ...dashboardQueries.databases(accessToken),
    refetchInterval: 5_000,
  });

  const schemaQuery = useQuery({
    ...dashboardQueries.schema(selectedDatabaseId ?? "", accessToken),
    enabled: Boolean(selectedDatabaseId),
  });

  const filteredTables = useMemo(() => {
    const tables = schemaQuery.data?.tables ?? [];
    if (!tableSearch.trim()) {
      return tables;
    }
    const query = tableSearch.toLowerCase();
    return tables.filter((table) => `${table.schema_name}.${table.name}`.toLowerCase().includes(query));
  }, [schemaQuery.data?.tables, tableSearch]);

  const selectedTable = filteredTables.find((table) => table.id === selectedTableId) ?? filteredTables[0];
  const servers = useMemo(() => serversQuery.data ?? [], [serversQuery.data]);
  const databases = useMemo(() => databasesQuery.data ?? [], [databasesQuery.data]);
  const serverById = useMemo(() => new Map(servers.map((server) => [server.id, server])), [servers]);
  const selectedServer = selectedServerId ? serverById.get(selectedServerId) : undefined;
  const selectedDatabase = useMemo(
    () => databases.find((database) => database.id === selectedDatabaseId),
    [databases, selectedDatabaseId]
  );

  const filteredDatabases = useMemo(() => {
    if (!selectedServer) {
      return databases;
    }
    const allowedDatabaseIds = new Set(selectedServer.databases.map((database) => database.id));
    return databases.filter((database) => allowedDatabaseIds.has(database.id));
  }, [databases, selectedServer]);

  const serversCount = serversQuery.data?.length ?? 0;
  const databasesCount = databasesQuery.data?.length ?? 0;
  const isSetupComplete = serversCount > 0 && databasesCount > 0;

  useEffect(() => {
    if (servers.length === 0) {
      if (selectedServerId || selectedDatabaseId) {
        void navigate({
          to: "/",
          search: (prev) => ({
            ...prev,
            serverId: undefined,
            dbId: undefined,
          }),
          replace: true,
        });
      }
      return;
    }

    const hasSelectedServer = selectedServerId && servers.some((server) => server.id === selectedServerId);
    if (!hasSelectedServer) {
      void navigate({
        to: "/",
        search: (prev) => ({
          ...prev,
          serverId: servers[0]?.id,
        }),
        replace: true,
      });
    }
  }, [navigate, selectedDatabaseId, selectedServerId, servers]);

  useEffect(() => {
    if (!selectedServer) {
      return;
    }

    if (filteredDatabases.length === 0) {
      if (selectedDatabaseId) {
        void navigate({
          to: "/",
          search: (prev) => ({
            ...prev,
            dbId: undefined,
          }),
          replace: true,
        });
      }
      return;
    }

    const hasSelectedDatabase = selectedDatabaseId && filteredDatabases.some((database) => database.id === selectedDatabaseId);
    if (!hasSelectedDatabase) {
      void navigate({
        to: "/",
        search: (prev) => ({
          ...prev,
          dbId: filteredDatabases[0]?.id,
        }),
        replace: true,
      });
      setSelectedTableId(null);
    }
  }, [filteredDatabases, navigate, selectedDatabaseId, selectedServer]);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-2 pb-6">
      <header className="mb-2 border-b border-border pb-6">
        <p className="sf-label font-mono text-accent-amber">Operations Console</p>
        <h1 className="mt-2 font-display text-3xl tracking-wide text-accent-cyan">PGWarden Dashboard</h1>
      </header>

      {!isSetupComplete ? (
        <>
          <section className="sf-panel p-6">
            <SetupEmptyState
              title="Start your monitoring setup"
              description="Create at least one server and one database to unlock the full dashboard experience."
              variant="dashboard"
              action={
                <div className="flex flex-wrap items-center justify-center gap-3">
                  <Link className="app-button-primary inline-flex items-center justify-center" to="/setup/servers">
                    Create server
                  </Link>
                  <Link
                    className="inline-flex items-center justify-center rounded-md border border-border px-4 py-2 text-sm text-muted-foreground transition hover:border-borderStrong hover:text-foreground"
                    to="/setup/databases"
                  >
                    Create database
                  </Link>
                </div>
              }
            />
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <article className="sf-panel p-4">
              <h2 className="sf-label text-accent-cyan">Servers monitored</h2>
              <p className="sf-metric mt-2 text-3xl font-semibold text-foreground">{serversCount}</p>
              <p className="mt-1 text-xs text-muted-foreground">Current configured servers.</p>
            </article>
            <article className="sf-panel p-4">
              <h2 className="sf-label text-accent-cyan">Databases managed</h2>
              <p className="sf-metric mt-2 text-3xl font-semibold text-foreground">{databasesCount}</p>
              <p className="mt-1 text-xs text-muted-foreground">Current registered databases.</p>
            </article>
          </section>

          <section className="grid gap-4 md:grid-cols-2">
            <Link
              to="/setup/servers"
              className="group rounded-md border border-borderStrong/70 bg-muted/20 px-4 py-4 shadow-panel transition hover:border-accent-cyan hover:bg-muted/40"
            >
              <p className="font-medium text-foreground">1. Register servers</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {serversCount > 0 ? `${serversCount} configured` : "No servers yet"}
              </p>
              <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-accent-cyan group-hover:text-accent-amber">
                Open server setup &#8594;
              </p>
            </Link>
            <Link
              to="/setup/databases"
              className="group rounded-md border border-borderStrong/70 bg-muted/20 px-4 py-4 shadow-panel transition hover:border-accent-cyan hover:bg-muted/40"
            >
              <p className="font-medium text-foreground">2. Register databases</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {databasesCount > 0 ? `${databasesCount} configured` : "No databases yet"}
              </p>
              <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-accent-cyan group-hover:text-accent-amber">
                Open database setup &#8594;
              </p>
            </Link>
          </section>
        </>
      ) : (
        <>
          <section className="sf-panel p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h2 className="sf-label text-accent-cyan">Current context</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Pick a server first, then choose the active database for schema exploration.
                </p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <select
                  className="app-input min-w-[220px]"
                  value={selectedServerId ?? ""}
                  onChange={(event) => {
                    const nextServerId = event.target.value || undefined;
                    setSelectedTableId(null);
                    void navigate({
                      to: "/",
                      search: (prev) => ({
                        ...prev,
                        serverId: nextServerId,
                        dbId: undefined,
                      }),
                      replace: true,
                    });
                  }}
                  disabled={servers.length === 0}
                >
                  <option value="">Select server</option>
                  {servers.map((server) => (
                    <option key={server.id} value={server.id}>
                      {server.name}
                    </option>
                  ))}
                </select>
                <select
                  className="app-input min-w-[220px]"
                  value={selectedDatabaseId ?? ""}
                  onChange={(event) => {
                    const nextDatabaseId = event.target.value || undefined;
                    setSelectedTableId(null);
                    void navigate({
                      to: "/",
                      search: (prev) => ({
                        ...prev,
                        dbId: nextDatabaseId,
                      }),
                      replace: true,
                    });
                  }}
                  disabled={!selectedServer || filteredDatabases.length === 0}
                >
                  <option value="">Select database</option>
                  {filteredDatabases.map((database) => (
                    <option key={database.id} value={database.id}>
                      {database.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-3">
            <article className="sf-panel p-4">
              <h2 className="sf-label text-accent-cyan">Servers monitored</h2>
              <p className="sf-metric mt-2 text-3xl font-semibold text-foreground">{serversCount}</p>
              <p className="mt-1 text-xs text-muted-foreground">Connection status and topology overview.</p>
            </article>
            <article className="sf-panel p-4">
              <h2 className="sf-label text-accent-cyan">Databases managed</h2>
              <p className="sf-metric mt-2 text-3xl font-semibold text-foreground">{databasesCount}</p>
              <p className="mt-1 text-xs text-muted-foreground">Choose a database below to inspect schema.</p>
            </article>
            <article className="sf-panel p-4">
              <h2 className="sf-label text-accent-cyan">Schema status</h2>
              <p className="sf-metric mt-2 text-3xl font-semibold text-foreground">
                {schemaQuery.data?.tables.length ?? 0}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {selectedDatabaseId ? "Tables loaded for selected database." : "Select a database to load schema."}
              </p>
            </article>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <article className="sf-panel p-4">
              <div className="flex items-center justify-between gap-2">
                <h2 className="sf-label text-accent-cyan">Servers</h2>
                <Link className="app-link" to="/setup/servers">
                  Manage servers
                </Link>
              </div>
              <div className="mt-3 space-y-2">
                {servers.map((server) => (
                  <div
                    key={server.id}
                    className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                      server.id === selectedServerId
                        ? "border-borderStrong bg-muted/45"
                        : "border-border bg-background/40"
                    }`}
                  >
                    <div>
                      <p className="font-medium text-foreground">{server.name}</p>
                      <p className="sf-label mt-1">{server.databases.length} databases linked</p>
                    </div>
                    <span className={`rounded border px-2 py-1 text-xs uppercase ${statusBadgeClass(server.status)}`}>
                      {server.status}
                    </span>
                  </div>
                ))}
                {serversQuery.isLoading ? <p className="text-xs text-muted-foreground">Loading servers...</p> : null}
              </div>
            </article>

            <article className="sf-panel p-4">
              <div className="flex items-center justify-between gap-2">
                <h2 className="sf-label text-accent-cyan">Databases</h2>
                <Link className="app-link" to="/setup/databases">
                  Manage databases
                </Link>
              </div>
              <div className="mt-3 space-y-2">
                {filteredDatabases.map((database) => {
                  const isSelected = selectedDatabaseId === database.id;
                  return (
                    <button
                      key={database.id}
                      type="button"
                      onClick={() => {
                        setSelectedTableId(null);
                        void navigate({
                          to: "/",
                          search: (prev) => ({
                            ...prev,
                            dbId: database.id,
                          }),
                          replace: true,
                        });
                      }}
                      className={`w-full rounded-md border px-3 py-2 text-left transition ${
                        isSelected
                          ? "border-borderStrong bg-muted/50"
                          : "border-border bg-background/40 hover:bg-muted/35"
                      }`}
                    >
                      <p className="font-medium text-foreground">{database.name}</p>
                      <p className="sf-label mt-1">{database.status ? "active" : "inactive"}</p>
                    </button>
                  );
                })}
                {databasesQuery.isLoading ? (
                  <p className="text-xs text-muted-foreground">Loading databases...</p>
                ) : null}
                {!databasesQuery.isLoading && selectedServer && filteredDatabases.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No databases linked to selected server.</p>
                ) : null}
              </div>
            </article>
          </section>

          <PerformanceChart
            selectedServerId={selectedServerId}
            selectedServerName={selectedServer?.name ?? null}
            selectedDatabaseId={selectedDatabaseId}
            selectedDatabaseName={selectedDatabase?.name ?? null}
          />

          <section className="sf-panel p-4 content-auto">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h2 className="sf-label text-accent-cyan">Schema explorer</h2>
              <input
                className="app-input max-w-sm"
                placeholder="Search tables..."
                value={tableSearch}
                onChange={(event) => setTableSearch(event.target.value)}
              />
            </div>

            {!selectedDatabaseId ? (
              <p className="text-sm text-muted-foreground">
                Select a database to inspect tables, columns and indexes.
              </p>
            ) : null}

            {schemaQuery.isLoading ? <p className="text-sm text-muted-foreground">Loading schema...</p> : null}
            {schemaQuery.isError ? (
              <p className="text-sm text-rose-300">
                {formatApiError(schemaQuery.error, "Failed to load schema for selected database.")}
              </p>
            ) : null}

            {selectedDatabaseId && schemaQuery.data ? (
              <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
                <div className="max-h-[460px] space-y-2 overflow-auto pr-1">
                  {filteredTables.map((table) => {
                    const isSelected = selectedTable?.id === table.id;
                    return (
                      <button
                        key={table.id}
                        type="button"
                        onClick={() => setSelectedTableId(table.id)}
                        className={`w-full rounded-md border px-3 py-2 text-left transition ${
                          isSelected
                            ? "border-borderStrong bg-muted/60"
                            : "border-border bg-background/35 hover:bg-muted/35"
                        }`}
                      >
                        <p className="font-medium text-foreground">{table.name}</p>
                        <p className="sf-label mt-1">{table.schema_name}</p>
                      </button>
                    );
                  })}
                </div>

                <div className="space-y-3 rounded-md border border-border bg-background/35 p-3">
                  {selectedTable ? (
                    <>
                      <div>
                        <p className="text-lg font-semibold text-foreground">{selectedTable.name}</p>
                        <p className="sf-label mt-1">{selectedTable.schema_name}</p>
                      </div>
                      <div>
                        <p className="sf-label text-foreground">Columns</p>
                        <div className="mt-2 max-h-[250px] overflow-auto rounded-md border border-border">
                          {selectedTable.columns.map((column) => (
                            <div
                              key={column.id}
                              className="grid grid-cols-[minmax(120px,1fr)_120px_90px] gap-3 border-b border-border/70 px-3 py-2 text-sm last:border-b-0"
                            >
                              <div>
                                <p className="font-medium text-foreground">{column.name}</p>
                                <p className="text-xs text-muted-foreground">{column.data_type}</p>
                              </div>
                              <p className="sf-label self-center">
                                {column.is_nullable ? "nullable" : "required"}
                              </p>
                              <p className="sf-label self-center">{column.is_unique ? "unique" : "-"}</p>
                            </div>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="sf-label text-foreground">Indexes</p>
                        <div className="mt-2 space-y-2">
                          {selectedTable.indexes.length === 0 ? (
                            <p className="text-xs text-muted-foreground">No indexes reported for this table.</p>
                          ) : (
                            selectedTable.indexes.map((index) => (
                              <div key={index.id} className="rounded-md border border-border px-3 py-2 text-sm">
                                <p className="font-medium text-foreground">{index.name}</p>
                                <p className="sf-label mt-1">
                                  {index.type} {index.is_unique ? "• unique" : ""}
                                </p>
                              </div>
                            ))
                          )}
                        </div>
                      </div>
                    </>
                  ) : (
                    <p className="text-sm text-muted-foreground">No tables found for this database.</p>
                  )}
                </div>
              </div>
            ) : null}
          </section>
        </>
      )}
    </div>
  );
}
