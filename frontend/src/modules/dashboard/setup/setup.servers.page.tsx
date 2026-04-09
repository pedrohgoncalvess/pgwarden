import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createServer } from "@/modules/dashboard/dashboard.api";
import type { CreateServerPayload } from "@/modules/dashboard/dashboard.schema";
import { formatApiError, statusBadgeClass } from "@/modules/dashboard/dashboard.ui";
import { SetupEmptyState } from "@/modules/dashboard/setup/setup.empty-state";
import { SetupLayout } from "@/modules/dashboard/setup/setup.layout";
import { SetupModal } from "@/modules/dashboard/setup/setup.modal";
import { useSetupQueries } from "@/modules/dashboard/setup/setup.queries";

const initialServerForm: CreateServerPayload = {
  name: "",
  host: "",
  port: "5432",
  username: "",
  password: "",
  ssl_mode: "prefer",
};

export function DashboardSetupServersPage() {
  const queryClient = useQueryClient();
  const { accessToken, serversQuery } = useSetupQueries();
  const [serverForm, setServerForm] = useState<CreateServerPayload>(initialServerForm);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const createServerMutation = useMutation({
    mutationFn: (payload: CreateServerPayload) => createServer(payload, accessToken ?? undefined),
    onSuccess: () => {
      setServerForm(initialServerForm);
      setIsCreateModalOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["dashboard", "servers"] });
    },
  });

  const handleCreateServer = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await createServerMutation.mutateAsync(serverForm);
  };

  const servers = serversQuery.data ?? [];

  return (
    <SetupLayout step="Setup • Step 1" title="Register servers">
      <section className="sf-panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="sf-label text-accent-cyan">Server inventory</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Add servers and keep track of their connection health before linking databases.
            </p>
          </div>
          <button type="button" className="app-button-primary" onClick={() => setIsCreateModalOpen(true)}>
            + New server
          </button>
        </div>
      </section>

      <section className="sf-panel p-5">
        <h2 className="sf-label text-accent-cyan">Registered servers</h2>

        {serversQuery.isLoading ? <p className="mt-4 text-sm text-muted-foreground">Loading servers...</p> : null}

        {!serversQuery.isLoading && servers.length === 0 ? (
          <div className="mt-4">
            <SetupEmptyState
              title="No servers connected yet"
              description="Start by creating your first server connection. This is the first step before registering any database."
              variant="servers"
              action={
                <button type="button" className="app-button-primary" onClick={() => setIsCreateModalOpen(true)}>
                  Create first server
                </button>
              }
            />
          </div>
        ) : null}

        {servers.length > 0 ? (
          <div className="mt-4 space-y-2">
            {servers.map((server) => (
              <div
                key={server.id}
                className="flex items-center justify-between rounded-md border border-border bg-background/40 px-4 py-3"
              >
                <div>
                  <p className="font-medium text-foreground">{server.name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{server.databases.length} databases linked</p>
                </div>
                <span className={`rounded border px-2 py-1 text-xs uppercase ${statusBadgeClass(server.status)}`}>
                  {server.status}
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      {isCreateModalOpen ? (
        <SetupModal
          title="Create server"
          description="Provide access credentials to connect this PostgreSQL server."
          onClose={() => setIsCreateModalOpen(false)}
        >
          <form className="grid gap-2" onSubmit={handleCreateServer}>
            <input
              className="app-input"
              placeholder="Server name"
              value={serverForm.name}
              onChange={(event) => setServerForm((state) => ({ ...state, name: event.target.value }))}
              required
            />
            <div className="grid gap-2 md:grid-cols-2">
              <input
                className="app-input"
                placeholder="Host"
                value={serverForm.host}
                onChange={(event) => setServerForm((state) => ({ ...state, host: event.target.value }))}
                required
              />
              <input
                className="app-input"
                placeholder="Port"
                value={serverForm.port}
                onChange={(event) => setServerForm((state) => ({ ...state, port: event.target.value }))}
                required
              />
            </div>
            <div className="grid gap-2 md:grid-cols-2">
              <input
                className="app-input"
                placeholder="Username"
                value={serverForm.username}
                onChange={(event) => setServerForm((state) => ({ ...state, username: event.target.value }))}
                required
              />
              <input
                className="app-input"
                placeholder="Password"
                type="password"
                value={serverForm.password}
                onChange={(event) => setServerForm((state) => ({ ...state, password: event.target.value }))}
                required
              />
            </div>
            {createServerMutation.isError ? (
              <p className="mt-1 text-xs text-rose-300">
                {formatApiError(createServerMutation.error, "Failed to register server.")}
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
              <button className="app-button-primary" disabled={createServerMutation.isPending}>
                {createServerMutation.isPending ? "Creating..." : "Create server"}
              </button>
            </div>
          </form>
        </SetupModal>
      ) : null}
    </SetupLayout>
  );
}
