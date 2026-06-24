<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { listDatabases, createSessionEventSource, formatBytes } from '$lib/api';
  import type { DatabaseListItem } from '$lib/api';

  type SessionRow = {
    pid: number;
    user_name: string | null;
    application_name: string | null;
    client_addr: string | null;
    state: string | null;
    wait_event_type: string | null;
    wait_event: string | null;
    query_start: string | null;
    query_preview: string | null;
    backend_start: string;
  };

  let databases = $state<DatabaseListItem[]>([]);
  let selectedDb = $state<DatabaseListItem | null>(null);
  let sessions = $state<SessionRow[]>([]);
  let loading = $state(true);
  let error = $state<string>('');
  let eventSource = $state<EventSource | null>(null);
  let connected = $state(false);

  async function loadDatabases() {
    try {
      loading = true;
      error = '';
      databases = await listDatabases();

      if (databases.length > 0) {
        selectedDb = databases[0];
        connectSessionsStream(selectedDb.id);
      }
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

  function connectSessionsStream(dbId: string) {
    if (eventSource) {
      eventSource.close();
      connected = false;
    }

    eventSource = createSessionEventSource(dbId);

    eventSource.onopen = () => {
      connected = true;
    };

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (Array.isArray(data)) {
          sessions = data;
        }
      } catch {
        // ignore malformed events
      }
    };

    eventSource.onerror = () => {
      connected = false;
    };
  }

  function selectDatabase(db: DatabaseListItem) {
    selectedDb = db;
    sessions = [];
    connectSessionsStream(db.id);
  }

  function stateBadgeColor(state: string | null): string {
    switch (state) {
      case 'active':
        return 'bg-primary/10 text-primary border-primary/20';
      case 'idle':
        return 'bg-surface-variant text-on-surface-variant border-outline-variant';
      case 'idle in transaction':
        return 'bg-tertiary/10 text-tertiary border-tertiary/20';
      default:
        return 'bg-error-container/10 text-error border-error/20';
    }
  }

  onMount(() => {
    loadDatabases();
  });

  onDestroy(() => {
    if (eventSource) {
      eventSource.close();
    }
  });
</script>

<!-- TopAppBar -->
<header class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16">
  <div class="flex items-center gap-4">
    <span class="material-symbols-outlined text-primary">group</span>
    <div class="flex items-center gap-3">
      <h1 class="font-headline-md text-headline-md text-on-background m-0">Active Sessions</h1>
      {#if selectedDb}
        <span class="text-[10px] font-label-caps text-on-surface-variant">
          {selectedDb.name}
        </span>
      {/if}
    </div>
  </div>
  <div class="flex items-center gap-4">
    {#if selectedDb}
      <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border {connected ? 'bg-primary/10 text-primary border-primary/20' : 'bg-error-container/10 text-error border-error/20'}">
        <span class="w-1.5 h-1.5 rounded-full mr-1.5 {connected ? 'bg-primary status-pulse' : 'bg-error'}"></span>
        {connected ? 'LIVE' : 'DISCONNECTED'}
      </span>
    {/if}
  </div>
</header>

<!-- Canvas -->
<div class="pt-24 px-container-padding pb-12">

  {#if loading}
    <div class="flex items-center justify-center py-12">
      <svg class="animate-spin h-8 w-8 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
    </div>
  {:else if databases.length === 0}
    <div class="flex flex-col items-center justify-center py-24">
      <div class="w-20 h-20 rounded-2xl bg-surface-container-high border border-outline-variant flex items-center justify-center mb-6">
        <span class="material-symbols-outlined text-[40px] text-on-surface-variant">group</span>
      </div>
      <h2 class="font-headline-md text-headline-md font-bold text-on-surface mb-2">No databases connected</h2>
      <p class="text-body-md text-on-surface-variant max-w-md text-center mb-8">
        Connect a database from the Overview page to monitor active sessions.
      </p>
      <a href="/dashboard" class="btn-primary px-8 py-3 font-bold text-sm flex items-center gap-2 cursor-pointer">
        <span class="material-symbols-outlined text-sm">dashboard</span>
        Go to Overview
      </a>
    </div>
  {:else}

    <!-- Database Selector -->
    <div class="mb-6 flex items-center gap-3">
      <span class="text-[10px] font-label-caps text-on-surface-variant uppercase tracking-widest">Database</span>
      <div class="flex items-center gap-2">
        {#each databases as db}
          <button
            onclick={() => selectDatabase(db)}
            class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer {selectedDb?.id === db.id ? 'bg-primary text-on-primary' : 'bg-surface-container border border-outline-variant text-on-surface-variant hover:bg-surface-variant'}"
          >
            {db.name}
          </button>
        {/each}
      </div>
    </div>

    <!-- Sessions Table -->
    <div class="bg-surface-container border border-outline-variant rounded-lg overflow-hidden">
      <div class="px-4 py-3 border-b border-outline-variant flex justify-between items-center bg-surface-container-low">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-primary text-sm">terminal</span>
          <h2 class="font-headline-md text-headline-md m-0">Active Sessions</h2>
          <span class="text-[10px] font-label-caps text-on-surface-variant ml-2">{sessions.length} sessions</span>
        </div>
      </div>

      {#if sessions.length === 0}
        <div class="p-8 text-center">
          <span class="material-symbols-outlined text-[32px] text-on-surface-variant mb-2">hourglass_empty</span>
          <p class="text-body-md text-on-surface-variant">No active sessions found.</p>
        </div>
      {:else}
        <div class="overflow-x-auto custom-scrollbar">
          <table class="w-full text-left border-collapse">
            <thead>
              <tr class="bg-surface-container-high">
                <th class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant">PID</th>
                <th class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant">USER</th>
                <th class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant">APPLICATION</th>
                <th class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant">CLIENT</th>
                <th class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant">STATE</th>
                <th class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant">WAIT EVENT</th>
                <th class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant">QUERY</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-variant/30">
              {#each sessions as session}
                <tr class="hover:bg-surface-variant/20 transition-colors">
                  <td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant">{session.pid}</td>
                  <td class="px-4 py-3 font-code-sm text-code-sm text-on-surface">{session.user_name || '-'}</td>
                  <td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant">{session.application_name || '-'}</td>
                  <td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant">{session.client_addr || '-'}</td>
                  <td class="px-4 py-3">
                    <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border {stateBadgeColor(session.state)}">
                      {session.state || 'unknown'}
                    </span>
                  </td>
                  <td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant">
                    {#if session.wait_event_type}
                      <span class="text-tertiary">{session.wait_event_type}</span>
                      {#if session.wait_event}
                        <span class="text-on-surface-variant"> / {session.wait_event}</span>
                      {/if}
                    {:else}
                      -
                    {/if}
                  </td>
                  <td class="px-4 py-3">
                    {#if session.query_preview}
                      <code class="font-code-sm text-code-sm text-on-surface block max-w-xs truncate" title={session.query_preview}>{session.query_preview}</code>
                    {:else}
                      <span class="text-on-surface-variant text-xs">-</span>
                    {/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>

  {/if}
</div>

<style>
  .btn-primary {
    background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-container) 100%);
    color: var(--color-on-primary-container);
    border-radius: 8px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 14px 0 rgba(20, 184, 166, 0.39);
  }
  .btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(20, 184, 166, 0.5);
  }
  .btn-primary:active {
    transform: translateY(0);
    box-shadow: 0 2px 8px rgba(20, 184, 166, 0.3);
  }
</style>
