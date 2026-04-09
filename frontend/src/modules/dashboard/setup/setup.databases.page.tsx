import { FormEvent, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createDatabase } from "@/modules/dashboard/dashboard.api";
import type { CreateDatabasePayload } from "@/modules/dashboard/dashboard.schema";
import { formatApiError } from "@/modules/dashboard/dashboard.ui";
import { SetupEmptyState } from "@/modules/dashboard/setup/setup.empty-state";
import { SetupLayout } from "@/modules/dashboard/setup/setup.layout";
import { SetupModal } from "@/modules/dashboard/setup/setup.modal";
import { useSetupQueries } from "@/modules/dashboard/setup/setup.queries";

const initialDatabaseForm: CreateDatabasePayload = {
  server_id: "",
  db_name: "",
};

export function DashboardSetupDatabasesPage() {
  const queryClient = useQueryClient();
  const { accessToken, serversQuery, databasesQuery, serversCount } = useSetupQueries();
  const [databaseForm, setDatabaseForm] = useState<CreateDatabasePayload>(initialDatabaseForm);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const createDatabaseMutation = useMutation({
    mutationFn: (payload: CreateDatabasePayload) => createDatabase(payload, accessToken ?? undefined),
    onSuccess: () => {
      setDatabaseForm((current) => ({ ...current, db_name: "" }));
      setIsCreateModalOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["dashboard", "databases"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard", "servers"] });
    },
  });

  const handleCreateDatabase = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await createDatabaseMutation.mutateAsync(databaseForm);
  };

  const servers = serversQuery.data ?? [];
  const databases = databasesQuery.data ?? [];

  return (
    <SetupLayout step="Setup • Step 2" title="Register databases">
      {serversCount === 0 ? (
        <section className="sf-panel p-5">
          <SetupEmptyState
            title="No servers available"
            description="You need at least one registered server before adding databases."
            variant="servers"
            action={
              <Link className="app-button-primary inline-flex items-center justify-center" to="/setup/servers">
                Go to server setup
              </Link>
            }
          />
        </section>
      ) : (
        <>
          <section className="sf-panel p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="sf-label text-accent-cyan">Database inventory</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Register databases for your connected servers and prepare monitoring.
                </p>
              </div>
              <button type="button" className="app-button-primary" onClick={() => setIsCreateModalOpen(true)}>
                + New database
              </button>
            </div>
          </section>

          <section className="sf-panel p-5">
            <h2 className="sf-label text-accent-cyan">Registered databases</h2>

            {databasesQuery.isLoading ? <p className="mt-4 text-sm text-muted-foreground">Loading databases...</p> : null}

            {!databasesQuery.isLoading && databases.length === 0 ? (
              <div className="mt-4">
                <SetupEmptyState
                  title="No databases registered"
                  description="Create your first database and link it to a server to unlock schema exploration in the dashboard."
                  variant="databases"
                  action={
                    <button type="button" className="app-button-primary" onClick={() => setIsCreateModalOpen(true)}>
                      Create first database
                    </button>
                  }
                />
              </div>
            ) : null}

            {databases.length > 0 ? (
              <div className="mt-4 space-y-2">
                {databases.map((database) => (
                  <div
                    key={database.id}
                    className="flex items-center justify-between rounded-md border border-border bg-background/40 px-4 py-3"
                  >
                    <p className="font-medium text-foreground">{database.name}</p>
                    <p className="text-xs uppercase text-muted-foreground">
                      {database.status ? "active" : "inactive"}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </>
      )}

      {isCreateModalOpen ? (
        <SetupModal
          title="Create database"
          description="Choose a server and register a database for monitoring."
          onClose={() => setIsCreateModalOpen(false)}
        >
          <form className="grid gap-2" onSubmit={handleCreateDatabase}>
            <select
              className="app-input"
              value={databaseForm.server_id}
              onChange={(event) => setDatabaseForm((state) => ({ ...state, server_id: event.target.value }))}
              required
            >
              <option value="">Select server</option>
              {servers.map((server) => (
                <option key={server.id} value={server.id}>
                  {server.name}
                </option>
              ))}
            </select>
            <input
              className="app-input"
              placeholder="Database name"
              value={databaseForm.db_name}
              onChange={(event) => setDatabaseForm((state) => ({ ...state, db_name: event.target.value }))}
              required
            />
            {createDatabaseMutation.isError ? (
              <p className="mt-1 text-xs text-rose-300">
                {formatApiError(createDatabaseMutation.error, "Failed to register database.")}
              </p>
            ) : null}
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-border px-3 py-2 text-sm text-muted-foreground transition hover:border-borderStrong hover:text-foreground"
                onClick={() => setIsCreateModalOpen(false)}
              >
                Cancel
              </button>
              <button className="app-button-primary" disabled={createDatabaseMutation.isPending}>
                {createDatabaseMutation.isPending ? "Creating..." : "Create database"}
              </button>
            </div>
          </form>
        </SetupModal>
      ) : null}
    </SetupLayout>
  );
}
