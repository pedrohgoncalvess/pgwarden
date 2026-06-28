<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
  import { listDatabases, listRunHistory } from '$lib/api';
  import type { DatabaseListItem, RunHistoryItem, RunType } from '$lib/api';

  // ── State ────────────────────────────────────────────────────────────────────
  let databases = $state<DatabaseListItem[]>([]);
  let selectedDb = $state<DatabaseListItem | null>(null);
  let history = $state<RunHistoryItem[]>([]);
  let loading = $state(true);
  let error = $state('');
  let offset = $state(0);
  const limit = 50;

  // ── Helpers ──────────────────────────────────────────────────────────────────
  function typeBadge(type: RunType | null): string {
    if (type === 'server') return 'bg-secondary/10 text-secondary border-secondary/20';
    if (type === 'database') return 'bg-primary/10 text-primary border-primary/20';
    return 'bg-outline/10 text-on-surface-variant border-outline-variant/30';
  }

  function statusBadge(status: string): string {
    if (status === 'success') return 'bg-primary/10 text-primary border-primary/20';
    if (status === 'error') return 'bg-error/10 text-error border-error/20';
    return 'bg-outline/10 text-on-surface-variant border-outline-variant/30';
  }

  function formatTime(iso: string | null): string {
    if (!iso) return '--';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '--';
    return d.toLocaleString();
  }

  function formatDuration(start: string | null, finish: string | null): string {
    if (!start || !finish) return '--';
    const ms = new Date(finish).getTime() - new Date(start).getTime();
    if (Number.isNaN(ms) || ms < 0) return '--';
    if (ms < 1000) return `${ms}ms`;
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    return `${m}m ${s % 60}s`;
  }

  async function loadDatabaseHistory(db: DatabaseListItem, resetOffset = true) {
    selectedDb = db;
    selectedDatabaseId.set(db.id);
    if (resetOffset) offset = 0;
    loading = true;
    error = '';
    try {
      history = await listRunHistory(db.id, limit, offset);
    } catch (err: any) {
      if (err.message?.includes('401')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
        return;
      }
      error = err.message || 'Failed to load run history.';
      history = [];
    } finally {
      loading = false;
    }
  }

  async function changePage(delta: number) {
    const nextOffset = Math.max(0, offset + delta * limit);
    if (!selectedDb || nextOffset === offset) return;
    offset = nextOffset;
    await loadDatabaseHistory(selectedDb, false);
  }

  async function load() {
    try {
      loading = true;
      error = '';
      databases = await listDatabases();
      if (databases.length === 0) {
        history = [];
        return;
      }

      const routeDbId = $page.params.database_id;
      const db = databases.find((d) => d.id === routeDbId) ?? databases[0];
      if (db.id !== routeDbId) {
        await goto(`/runs/${db.id}/history`, { replaceState: true });
        return;
      }
      await loadDatabaseHistory(db);
    } catch (err: any) {
      if (err.message?.includes('401')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
        return;
      }
      error = err.message || 'Failed to load databases.';
    } finally {
      loading = false;
    }
  }

  onMount(() => load());
</script>

<!-- ── Top Bar ─────────────────────────────────────────────────────────────── -->
<header class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16">
  <div class="flex items-center gap-3">
    <span class="material-symbols-outlined text-primary">history</span>
    <h1 class="font-headline-md text-headline-md text-on-background m-0">Run History</h1>
    {#if selectedDb}
      <span class="font-label-caps text-[10px] text-on-surface-variant">{selectedDb.name}</span>
    {/if}
  </div>
  <button
    onclick={load}
    class="flex items-center gap-2 px-4 py-2 bg-surface-container border border-outline-variant text-on-surface rounded-lg font-bold text-sm hover:border-primary/40 hover:text-primary transition-all duration-200 cursor-pointer"
  >
    <span class="material-symbols-outlined text-sm">refresh</span>
    Refresh
  </button>
</header>

<!-- ── Canvas ─────────────────────────────────────────────────────────────── -->
<div class="pt-24 px-container-padding pb-12">

  {#if error}
    <div class="mb-6 p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3">
      <span class="material-symbols-outlined text-error">error</span>
      <p class="font-code-sm text-sm text-error">{error}</p>
    </div>
  {/if}

  {#if loading && databases.length === 0}
    <div class="flex items-center justify-center py-12">
      <svg class="h-8 w-8 animate-spin text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
    </div>
  {:else if databases.length === 0}
    <div class="flex flex-col items-center justify-center py-24">
      <div class="w-20 h-20 rounded-2xl bg-surface-container-high border border-outline-variant flex items-center justify-center mb-6">
        <span class="material-symbols-outlined text-[40px] text-on-surface-variant">database</span>
      </div>
      <h2 class="font-headline-md text-headline-md font-bold text-on-surface mb-2">No databases connected</h2>
      <p class="text-body-md text-on-surface-variant max-w-md text-center mb-8">
        Connect a database from the Servers page to view collector run history.
      </p>
    </div>
  {:else}
    <!-- Database selector -->
    <div class="mb-6 flex flex-wrap items-center gap-3">
      <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Database</span>
      {#each databases as db}
        <button
          onclick={() => loadDatabaseHistory(db)}
          class="cursor-pointer rounded-lg px-3 py-1.5 text-xs font-bold transition-all {selectedDb?.id === db.id ? 'bg-primary text-on-primary' : 'border border-outline-variant bg-surface-container text-on-surface-variant hover:bg-surface-variant'}"
        >
          {db.name}
        </button>
      {/each}
    </div>

    <!-- History table -->
    <section class="overflow-hidden rounded-lg border border-outline-variant bg-surface-container">
      <div class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-sm text-primary">history</span>
          <h2 class="m-0 font-headline-md text-headline-md">Execution History</h2>
        </div>
        <span class="font-code-sm text-code-sm text-on-surface-variant">
          {history.length} runs
        </span>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead class="bg-surface-container-high">
            <tr>
              <th class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest">NAME</th>
              <th class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest">TYPE</th>
              <th class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest">SCOPE</th>
              <th class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest">STATUS</th>
              <th class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest">STARTED</th>
              <th class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest">DURATION</th>
              <th class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest">ERRORS</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-outline-variant/20">
            {#if loading}
              <tr>
                <td colspan="7" class="px-4 py-8 text-center text-on-surface-variant text-sm">
                  <div class="flex items-center justify-center gap-2">
                    <svg class="animate-spin h-4 w-4 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Loading history…
                  </div>
                </td>
              </tr>
            {:else if history.length === 0}
              <tr>
                <td colspan="7" class="px-4 py-8 text-center text-on-surface-variant text-sm">
                  No run history found for this database.
                </td>
              </tr>
            {:else}
              {#each history as run (run.id)}
                <tr class="hover:bg-surface-variant/20 transition-colors">
                  <td class="px-4 py-3 font-code-sm text-code-sm text-on-surface font-bold">{run.name || '--'}</td>
                  <td class="px-4 py-3">
                    <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border {typeBadge(run.type)}">
                      {run.type || 'unknown'}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-sm text-on-surface-variant">
                    {#if run.database_name}
                      {run.database_name}
                    {:else}
                      <span class="text-on-surface-variant">server-wide</span>
                    {/if}
                  </td>
                  <td class="px-4 py-3">
                    <span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold border {statusBadge(run.status)}">
                      {run.status}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-sm text-on-surface-variant">{formatTime(run.started_at)}</td>
                  <td class="px-4 py-3 font-code-sm text-code-sm text-on-surface">{formatDuration(run.started_at, run.finished_at)}</td>
                  <td class="px-4 py-3 text-sm">
                    {#if run.errors && run.errors.length > 0}
                      <span class="text-error" title={run.errors.join('\n')}>
                        {run.errors.length} error{run.errors.length !== 1 ? 's' : ''}
                      </span>
                    {:else}
                      <span class="text-on-surface-variant">--</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="flex items-center justify-between border-t border-outline-variant px-4 py-3">
        <button
          onclick={() => changePage(-1)}
          disabled={offset === 0 || loading}
          class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-on-surface text-xs font-bold hover:bg-surface-variant disabled:opacity-50 cursor-pointer"
        >
          <span class="material-symbols-outlined text-[14px]">chevron_left</span>
          Previous
        </button>
        <span class="text-xs text-on-surface-variant font-code-sm">
          Page {Math.floor(offset / limit) + 1}
        </span>
        <button
          onclick={() => changePage(1)}
          disabled={history.length < limit || loading}
          class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-on-surface text-xs font-bold hover:bg-surface-variant disabled:opacity-50 cursor-pointer"
        >
          Next
          <span class="material-symbols-outlined text-[14px]">chevron_right</span>
        </button>
      </div>
    </section>
  {/if}
</div>
