<script lang="ts">
  import { onMount } from 'svelte';
  import {
    listServers, listDatabases,
    deleteServer, deleteDatabase,
  } from '$lib/api';
  import type { ServerListItem, DatabaseListItem } from '$lib/api';

  // ── Tab system ─────────────────────────────────────────────────────────────
  type Topic = { id: string; label: string; icon: string; available: boolean };

  const topics: Topic[] = [
    { id: 'connections', label: 'Connections',  icon: 'lan',         available: true  },
    { id: 'collector',   label: 'Collector',    icon: 'radar',       available: false },
    { id: 'alerts',      label: 'Alerts',       icon: 'notifications',available: false },
    { id: 'account',     label: 'Account',      icon: 'manage_accounts', available: false },
  ];

  let activeTopic = $state('connections');

  // ── Data ───────────────────────────────────────────────────────────────────
  let servers    = $state<ServerListItem[]>([]);
  let databases  = $state<DatabaseListItem[]>([]);
  let loading    = $state(true);
  let loadError  = $state('');

  async function load() {
    try {
      loading   = true;
      loadError = '';
      [servers, databases] = await Promise.all([listServers(), listDatabases()]);
    } catch (err: any) {
      if (err.message?.includes('401')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
        return;
      }
      loadError = err.message || 'Failed to load data.';
    } finally {
      loading = false;
    }
  }

  // ── Helper ─────────────────────────────────────────────────────────────────
  function getDatabasesForServer(serverId: string): DatabaseListItem[] {
    return databases.filter(d => d.server_id === serverId);
  }

  function getStatusBadge(status: string) {
    if (status === 'healthy') return { cls: 'bg-primary/10 text-primary border-primary/20',  dot: 'bg-primary', label: 'Healthy' };
    if (status === 'pending') return { cls: 'bg-tertiary/10 text-tertiary border-tertiary/20', dot: 'bg-tertiary', label: 'Pending' };
    return { cls: 'bg-error/10 text-error border-error/20', dot: 'bg-error', label: 'Error' };
  }

  // ── Delete flow ────────────────────────────────────────────────────────────
  type DeleteTarget =
    | { kind: 'server'; item: ServerListItem }
    | { kind: 'database'; item: DatabaseListItem };

  let deleteTarget  = $state<DeleteTarget | null>(null);
  let confirmInput  = $state('');
  let deleting      = $state(false);
  let deleteError   = $state('');

  function openDeleteModal(target: DeleteTarget) {
    deleteTarget = target;
    confirmInput = '';
    deleteError  = '';
  }

  function closeDeleteModal() {
    if (deleting) return;
    deleteTarget = null;
  }

  function expectedName(): string {
    if (!deleteTarget) return '';
    return deleteTarget.kind === 'server'
      ? deleteTarget.item.name
      : deleteTarget.item.name;
  }

  function canConfirm(): boolean {
    return confirmInput.trim() === expectedName();
  }

  async function confirmDelete() {
    if (!deleteTarget || !canConfirm()) return;
    deleting     = true;
    deleteError  = '';
    try {
      if (deleteTarget.kind === 'server') {
        await deleteServer(deleteTarget.item.id);
      } else {
        await deleteDatabase(deleteTarget.item.id);
      }
      deleteTarget = null;
      await load();
    } catch (err: any) {
      deleteError = err.message || 'Deletion failed.';
    } finally {
      deleting = false;
    }
  }

  onMount(() => load());
</script>

<style>
  .topic-tab {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 500;
    color: var(--color-on-surface-variant);
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease;
    border: none;
    background: none;
    width: 100%;
    text-align: left;
  }
  .topic-tab:hover:not(.unavailable) {
    background: rgba(133, 148, 144, 0.08);
    color: var(--color-on-surface);
  }
  .topic-tab.active {
    background: rgba(79, 219, 200, 0.12);
    color: var(--color-primary);
    font-weight: 700;
  }
  .topic-tab.unavailable {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .settings-card {
    background: rgba(26, 33, 31, 0.95);
    border: 1px solid rgba(133, 148, 144, 0.15);
    border-radius: 14px;
  }
  .danger-zone {
    border: 1px solid rgba(239, 68, 68, 0.25);
    border-radius: 12px;
    background: rgba(239, 68, 68, 0.04);
  }
  .danger-zone-header {
    border-bottom: 1px solid rgba(239, 68, 68, 0.15);
  }
  .row-item {
    border-bottom: 1px solid rgba(133, 148, 144, 0.08);
    transition: background 0.15s ease;
  }
  .row-item:last-child { border-bottom: none; }
  .row-item:hover { background: rgba(133, 148, 144, 0.03); }
  .modal-overlay {
    background: rgba(0, 0, 0, 0.65);
    backdrop-filter: blur(5px);
  }
  .skeleton {
    background: linear-gradient(90deg, rgba(133,148,144,0.08) 25%, rgba(133,148,144,0.16) 50%, rgba(133,148,144,0.08) 75%);
    background-size: 200% 100%;
    animation: skeleton-shine 1.5s infinite;
    border-radius: 4px;
  }
  @keyframes skeleton-shine {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
</style>

<!-- ── Delete Confirmation Modal ────────────────────────────────────────── -->
{#if deleteTarget}
  {@const name = expectedName()}
  {@const isServer = deleteTarget.kind === 'server'}

  <div class="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4">
    <div class="settings-card w-full max-w-md p-8 shadow-floating">

      <!-- Header -->
      <div class="flex items-start gap-4 mb-6">
        <div class="w-10 h-10 rounded-xl bg-error/10 border border-error/20 flex items-center justify-center flex-shrink-0 mt-0.5">
          <span class="material-symbols-outlined text-error text-[20px]">warning</span>
        </div>
        <div>
          <h2 class="font-headline-md text-headline-md font-bold text-on-surface m-0">
            Delete {isServer ? 'Server' : 'Database'}
          </h2>
          <p class="text-[12px] text-on-surface-variant mt-1 leading-relaxed">
            {#if isServer}
              This will permanently delete <span class="text-on-surface font-bold">"{name}"</span> and
              <span class="text-error font-semibold">all databases, sessions, locks, metrics, schemas,
              configs and tags</span> associated with it.
            {:else}
              This will permanently delete <span class="text-on-surface font-bold">"{name}"</span> and
              <span class="text-error font-semibold">all sessions, locks, metrics, schemas and configs</span>
              collected for it.
            {/if}
          </p>
        </div>
      </div>

      <!-- Confirm input -->
      <div class="mb-5">
        <label class="block text-xs font-bold text-on-surface-variant uppercase tracking-wider mb-2"
          for="confirm-name">
          Type <span class="text-error font-mono">{name}</span> to confirm
        </label>
        <input
          id="confirm-name"
          bind:value={confirmInput}
          placeholder={name}
          class="w-full bg-surface-container-low border border-error/30 focus:border-error text-on-surface font-mono text-sm px-4 py-2.5 rounded-lg outline-none transition-colors placeholder:text-on-surface-variant/40"
          autocomplete="off"
          spellcheck="false"
        />
      </div>

      {#if deleteError}
        <div class="mb-4 px-4 py-3 bg-error-container/20 border border-error/30 rounded-lg flex items-center gap-2">
          <span class="material-symbols-outlined text-error text-[16px]">error</span>
          <p class="text-sm text-error">{deleteError}</p>
        </div>
      {/if}

      <!-- Actions -->
      <div class="flex gap-3">
        <button
          onclick={closeDeleteModal}
          disabled={deleting}
          class="flex-1 py-2.5 rounded-lg border border-outline-variant text-on-surface-variant font-bold text-sm hover:border-outline hover:text-on-surface transition-colors disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
        >
          Cancel
        </button>
        <button
          onclick={confirmDelete}
          disabled={!canConfirm() || deleting}
          class="flex-1 py-2.5 rounded-lg bg-error text-white font-bold text-sm flex items-center justify-center gap-2
                 hover:bg-error/90 active:scale-95 transition-all
                 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100 cursor-pointer"
        >
          {#if deleting}
            <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Deleting…
          {:else}
            <span class="material-symbols-outlined text-sm">delete_forever</span>
            Delete {isServer ? 'Server' : 'Database'}
          {/if}
        </button>
      </div>
    </div>
  </div>
{/if}

<!-- ── Top Bar ──────────────────────────────────────────────────────────── -->
<header class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3">
  <span class="material-symbols-outlined text-on-surface-variant">settings</span>
  <h1 class="font-headline-md text-headline-md text-on-background m-0">Settings</h1>
</header>

<!-- ── Canvas ───────────────────────────────────────────────────────────── -->
<div class="pt-24 px-container-padding pb-12">
  <div class="flex gap-8 items-start">

    <!-- ── Topic Sidebar ──────────────────────────────────────────────── -->
    <aside class="w-52 flex-shrink-0 sticky top-24">
      <p class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-3 px-1">Topics</p>
      <nav class="space-y-1">
        {#each topics as topic}
          <button
            onclick={() => { if (topic.available) activeTopic = topic.id; }}
            class="topic-tab {activeTopic === topic.id ? 'active' : ''} {!topic.available ? 'unavailable' : ''}"
          >
            <span class="material-symbols-outlined text-[18px]"
              style={activeTopic === topic.id ? "font-variation-settings: 'FILL' 1;" : ""}>
              {topic.icon}
            </span>
            <span>{topic.label}</span>
            {#if !topic.available}
              <span class="ml-auto text-[9px] font-bold uppercase tracking-wider opacity-60">Soon</span>
            {/if}
          </button>
        {/each}
      </nav>
    </aside>

    <!-- ── Topic Content ──────────────────────────────────────────────── -->
    <div class="flex-1 min-w-0 space-y-8">

      <!-- ═══════════════════════════════════════════════════════════════ -->
      <!-- TOPIC: Connections                                              -->
      <!-- ═══════════════════════════════════════════════════════════════ -->
      {#if activeTopic === 'connections'}

        <!-- Section header -->
        <div class="pb-4 border-b border-outline-variant">
          <h2 class="font-headline-md text-headline-md font-bold text-on-surface m-0">Connections</h2>
          <p class="text-sm text-on-surface-variant mt-1">
            Manage registered PostgreSQL servers and the databases linked to them.
          </p>
        </div>

        {#if loadError}
          <div class="p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3">
            <span class="material-symbols-outlined text-error">error</span>
            <p class="text-sm text-error">{loadError}</p>
          </div>
        {/if}

        {#if loading}
          <!-- Skeleton -->
          <div class="settings-card p-6 space-y-4">
            {#each [1, 2] as _}
              <div class="flex items-center justify-between">
                <div class="space-y-2">
                  <div class="skeleton h-4 w-40"></div>
                  <div class="skeleton h-3 w-24"></div>
                </div>
                <div class="skeleton h-8 w-24 rounded-lg"></div>
              </div>
            {/each}
          </div>

        {:else if servers.length === 0}
          <div class="settings-card px-6 py-12 flex flex-col items-center text-center">
            <span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3">dns</span>
            <p class="text-on-surface font-bold mb-1">No servers registered</p>
            <p class="text-sm text-on-surface-variant">Add a server from the main dashboard to get started.</p>
          </div>

        {:else}

          <!-- ── Servers ──────────────────────────────────────────────── -->
          <section>
            <div class="flex items-center gap-2 mb-3">
              <span class="material-symbols-outlined text-on-surface-variant text-[16px]">dns</span>
              <h3 class="text-sm font-bold uppercase tracking-wider text-on-surface-variant m-0">Servers</h3>
              <span class="text-[11px] text-on-surface-variant bg-surface-container px-2 py-0.5 rounded-full border border-outline-variant">{servers.length}</span>
            </div>

            <div class="settings-card overflow-hidden">
              {#each servers as server (server.id)}
                {@const badge = getStatusBadge(server.status)}
                {@const dbCount = getDatabasesForServer(server.id).length}

                <div class="row-item px-5 py-4 flex items-center justify-between gap-4">
                  <!-- Info -->
                  <div class="flex items-center gap-4 min-w-0">
                    <div class="w-9 h-9 rounded-lg bg-surface-container-high border border-outline-variant/50 flex items-center justify-center flex-shrink-0">
                      <span class="material-symbols-outlined text-on-surface-variant text-[16px]">dns</span>
                    </div>
                    <div class="min-w-0">
                      <p class="font-bold text-on-surface text-sm truncate">{server.name}</p>
                      <p class="text-[11px] text-on-surface-variant mt-0.5">
                        {dbCount} database{dbCount !== 1 ? 's' : ''}
                      </p>
                    </div>
                  </div>

                  <!-- Right side -->
                  <div class="flex items-center gap-3 flex-shrink-0">
                    <span class="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold border {badge.cls}">
                      <span class="w-1.5 h-1.5 rounded-full {badge.dot}"></span>
                      {badge.label}
                    </span>
                    <button
                      onclick={() => openDeleteModal({ kind: 'server', item: server })}
                      class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-error/30 text-error text-xs font-bold
                             hover:bg-error/10 hover:border-error/50 transition-all cursor-pointer"
                      title="Delete server and all its data"
                    >
                      <span class="material-symbols-outlined text-[14px]">delete</span>
                      Remove
                    </button>
                  </div>
                </div>
              {/each}
            </div>
          </section>

          <!-- ── Databases ───────────────────────────────────────────── -->
          <section>
            <div class="flex items-center gap-2 mb-3">
              <span class="material-symbols-outlined text-on-surface-variant text-[16px]">database</span>
              <h3 class="text-sm font-bold uppercase tracking-wider text-on-surface-variant m-0">Databases</h3>
              <span class="text-[11px] text-on-surface-variant bg-surface-container px-2 py-0.5 rounded-full border border-outline-variant">{databases.length}</span>
            </div>

            <div class="settings-card overflow-hidden">
              {#if databases.length === 0}
                <div class="px-6 py-8 text-center text-sm text-on-surface-variant">
                  No databases linked yet.
                </div>
              {:else}
                {#each databases as db (db.id)}
                  {@const parentServer = servers.find(s => s.id === db.server_id)}

                  <div class="row-item px-5 py-4 flex items-center justify-between gap-4">
                    <!-- Info -->
                    <div class="flex items-center gap-4 min-w-0">
                      <div class="w-9 h-9 rounded-lg bg-surface-container-high border border-outline-variant/50 flex items-center justify-center flex-shrink-0">
                        <span class="material-symbols-outlined text-primary text-[16px]"
                          style="font-variation-settings: 'FILL' 1;">database</span>
                      </div>
                      <div class="min-w-0">
                        <p class="font-bold text-on-surface text-sm font-mono truncate">{db.name}</p>
                        <p class="text-[11px] text-on-surface-variant mt-0.5">
                          {parentServer ? parentServer.name : 'Unknown server'}
                        </p>
                      </div>
                    </div>

                    <!-- Right side -->
                    <div class="flex items-center gap-3 flex-shrink-0">
                      {#if !db.status}
                        <span class="hidden sm:inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold bg-error/10 text-error border border-error/20">
                          Inactive
                        </span>
                      {:else}
                        <span class="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold bg-primary/10 text-primary border border-primary/20">
                          <span class="w-1.5 h-1.5 rounded-full bg-primary"></span>
                          Active
                        </span>
                      {/if}
                      <button
                        onclick={() => openDeleteModal({ kind: 'database', item: db })}
                        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-error/30 text-error text-xs font-bold
                               hover:bg-error/10 hover:border-error/50 transition-all cursor-pointer"
                        title="Delete database and all its collected data"
                      >
                        <span class="material-symbols-outlined text-[14px]">delete</span>
                        Remove
                      </button>
                    </div>
                  </div>
                {/each}
              {/if}
            </div>
          </section>

          <!-- ── Danger Zone ─────────────────────────────────────────── -->
          <section>
            <div class="danger-zone overflow-hidden">
              <!-- Header -->
              <div class="danger-zone-header px-5 py-4 flex items-center gap-3">
                <span class="material-symbols-outlined text-error text-[18px]">dangerous</span>
                <div>
                  <h3 class="text-sm font-bold text-error m-0 uppercase tracking-wider">Danger Zone</h3>
                  <p class="text-[11px] text-on-surface-variant mt-0.5">
                    Irreversible actions — all collected data will be permanently erased.
                  </p>
                </div>
              </div>

              <!-- Items -->
              <div class="divide-y divide-error/10">

                <!-- Delete all databases of a server -->
                {#each servers as server (server.id)}
                  {@const dbCount = getDatabasesForServer(server.id).length}
                  <div class="px-5 py-4 flex items-center justify-between gap-4">
                    <div>
                      <p class="text-sm font-bold text-on-surface">
                        Delete server <span class="text-error font-mono">"{server.name}"</span>
                      </p>
                      <p class="text-[11px] text-on-surface-variant mt-0.5">
                        Permanently removes the server and its {dbCount} database{dbCount !== 1 ? 's' : ''} with all collected data.
                      </p>
                    </div>
                    <button
                      onclick={() => openDeleteModal({ kind: 'server', item: server })}
                      class="flex-shrink-0 flex items-center gap-2 px-4 py-2 rounded-lg bg-error/10 border border-error/40 text-error text-xs font-bold
                             hover:bg-error/20 active:scale-95 transition-all cursor-pointer"
                    >
                      <span class="material-symbols-outlined text-[14px]">delete_forever</span>
                      Delete Server
                    </button>
                  </div>
                {/each}

              </div>
            </div>
          </section>
        {/if}

      <!-- ═══════════════════════════════════════════════════════════════ -->
      <!-- TOPIC: Placeholders                                            -->
      <!-- ═══════════════════════════════════════════════════════════════ -->
      {:else}
        <div class="settings-card px-6 py-16 flex flex-col items-center text-center">
          <span class="material-symbols-outlined text-[48px] text-on-surface-variant mb-4">
            {topics.find(t => t.id === activeTopic)?.icon ?? 'settings'}
          </span>
          <p class="font-bold text-on-surface text-lg mb-2">
            {topics.find(t => t.id === activeTopic)?.label} settings
          </p>
          <p class="text-sm text-on-surface-variant max-w-xs">
            This section is coming soon. Check back in a future release.
          </p>
        </div>
      {/if}

    </div>
  </div>
</div>
