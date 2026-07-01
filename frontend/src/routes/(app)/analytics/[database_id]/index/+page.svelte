<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
  import { listDatabases, getIndexAnalytics, formatBytes, formatNumber } from '$lib/api';
  import type {
    DatabaseListItem,
    IndexAnalyticsResponse,
    IndexAnalyticsItem,
    AnalyticsPreset
  } from '$lib/api';

  // ── State ────────────────────────────────────────────────────────────────────
  let databases = $state<DatabaseListItem[]>([]);
  let selectedDb = $state<DatabaseListItem | null>(null);
  let data = $state<IndexAnalyticsResponse | null>(null);
  let loading = $state(true);
  let error = $state('');

  let preset = $state<AnalyticsPreset>('1w');
  let startDate = $state('');
  let endDate = $state('');
  let selectedTableIds = $state<number[]>([]);
  let selectedIndexIds = $state<number[]>([]);
  let searchTerm = $state('');

  let tableDropdownOpen = $state(false);
  let indexDropdownOpen = $state(false);
  let tableSearchTerm = $state('');
  let indexSearchTerm = $state('');
  let chartHelpOpen = $state(false);
  let expandedIndex = $state<number | null>(null);
  let timelineHoverIndex = $state<number | null>(null);
  let tablePageOffset = $state(0);
  const tablePageLimit = 15;

  const presets: { label: string; value: AnalyticsPreset }[] = [
    { label: '1D', value: '1d' },
    { label: '3D', value: '3d' },
    { label: '1W', value: '1w' },
    { label: '2W', value: '2w' },
    { label: '1M', value: '1m' },
    { label: 'Custom', value: 'custom' }
  ];

  const colors = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'];

  // ── Helpers ──────────────────────────────────────────────────────────────────
  function toInputDate(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toISOString().slice(0, 16);
  }

  function fromInputDate(value: string): string {
    if (!value) return '';
    return new Date(value).toISOString();
  }

  function formatPercent(value: number | null): string {
    if (value === null || value === undefined) return '--';
    return `${(value * 100).toFixed(1)}%`;
  }

  function displayTableName(table: { schema_name: string; name?: string; table_name?: string }): string {
    const name = table.name ?? table.table_name ?? '';
    return table.schema_name === 'public' ? name : `${table.schema_name}.${name}`;
  }

  // ── Data loading ─────────────────────────────────────────────────────────────
  async function loadData(database: DatabaseListItem) {
    selectedDb = database;
    selectedDatabaseId.set(database.id);
    loading = true;
    error = '';
    tablePageOffset = 0;
    try {
      const options: Parameters<typeof getIndexAnalytics>[1] = {};
      if (preset === 'custom') {
        options.startDate = startDate ? fromInputDate(startDate) : undefined;
        options.endDate = endDate ? fromInputDate(endDate) : undefined;
      } else {
        options.preset = preset;
      }
      if (selectedTableIds.length > 0) options.tableIds = selectedTableIds;
      if (selectedIndexIds.length > 0) options.indexIds = selectedIndexIds;
      if (searchTerm.trim()) options.search = searchTerm.trim();

      data = await getIndexAnalytics(database.id, options);

      const existingTableIds = new Set(data.tables.map((t) => t.id));
      const existingIndexIds = new Set(data.indexes.map((i) => i.id));
      selectedTableIds = selectedTableIds.filter((id) => existingTableIds.has(id));
      selectedIndexIds = selectedIndexIds.filter((id) => existingIndexIds.has(id));
    } catch (err: any) {
      if (err.message?.includes('401')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
        return;
      }
      error = err.message || 'Failed to load index analytics.';
      data = null;
    } finally {
      loading = false;
    }
  }

  async function selectDatabase(database: DatabaseListItem, replace = false) {
    if (replace) {
      await goto(`/analytics/${database.id}/index`, { replaceState: true });
    }
    await loadData(database);
  }

  async function applyFilters() {
    if (!selectedDb) return;
    await loadData(selectedDb);
  }

  async function load() {
    try {
      loading = true;
      error = '';
      databases = await listDatabases();
      if (databases.length === 0) {
        return;
      }

      const routeDbId = $page.params.database_id;
      const db = databases.find((d) => d.id === routeDbId) ?? databases[0];
      if (db.id !== routeDbId) {
        await goto(`/analytics/${db.id}/index`, { replaceState: true });
        return;
      }
      await selectDatabase(db);
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

  function toggleTable(id: number) {
    if (selectedTableIds.includes(id)) {
      selectedTableIds = selectedTableIds.filter((x) => x !== id);
    } else {
      selectedTableIds = [...selectedTableIds, id];
    }
  }

  function toggleIndex(id: number) {
    if (selectedIndexIds.includes(id)) {
      selectedIndexIds = selectedIndexIds.filter((x) => x !== id);
    } else {
      selectedIndexIds = [...selectedIndexIds, id];
    }
  }

  // ── Derived state ────────────────────────────────────────────────────────────
  let filteredIndexes = $derived.by(() => {
    const currentData = data;
    if (!currentData) return [];
    return currentData.indexes.filter((idx) => {
      if (selectedTableIds.length > 0 && !selectedTableIds.includes(idx.table_id)) return false;
      return true;
    });
  });

  let searchedTables = $derived.by(() => {
    const currentData = data;
    if (!currentData) return [];
    const term = tableSearchTerm.trim().toLowerCase();
    if (!term) return currentData.tables;
    return currentData.tables.filter((t) => displayTableName(t).toLowerCase().includes(term));
  });

  let searchedIndexes = $derived.by(() => {
    const currentData = data;
    if (!currentData) return [];
    const term = indexSearchTerm.trim().toLowerCase();
    let list = filteredIndexes;
    if (!term) return list;
    return list.filter((idx) =>
      idx.index_name.toLowerCase().includes(term) ||
      displayTableName({ schema_name: idx.schema_name, table_name: idx.table_name }).toLowerCase().includes(term)
    );
  });

  // ── Chart helpers ────────────────────────────────────────────────────────────
  let timelineChartWidth = $state(0);
  const timelineChartHeight = 260;
  const padding = { top: 16, right: 48, bottom: 40, left: 56 };

  function xScale(index: number, count: number): number {
    if (count <= 1) return padding.left;
    const usableWidth = timelineChartWidth - padding.left - padding.right;
    return padding.left + (index / (count - 1)) * usableWidth;
  }

  function yScale(value: number, maxValue: number): number {
    const usableHeight = timelineChartHeight - padding.top - padding.bottom;
    if (maxValue <= 0) return padding.top + usableHeight;
    return padding.top + usableHeight - (value / maxValue) * usableHeight;
  }

  function yScaleHitRate(value: number | null): number {
    const usableHeight = timelineChartHeight - padding.top - padding.bottom;
    if (value === null || value === undefined) return padding.top + usableHeight;
    return padding.top + usableHeight - value * usableHeight;
  }

  function formatChartDate(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function handleTimelineMouseMove(event: MouseEvent) {
    if (!data || data.timeline.length === 0) return;
    const svg = event.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const usableWidth = timelineChartWidth - padding.left - padding.right;
    const ratio = Math.max(0, Math.min(1, (x - padding.left) / usableWidth));
    const index = Math.round(ratio * (data.timeline.length - 1));
    timelineHoverIndex = Math.max(0, Math.min(data.timeline.length - 1, index));
  }

  function handleTimelineMouseLeave() {
    timelineHoverIndex = null;
  }

  let timelineSizePoints = $derived.by(() => {
    const currentData = data;
    if (!currentData || currentData.timeline.length === 0) return [];
    const maxSize = Math.max(...currentData.timeline.map((p) => p.total_size_bytes), 1);
    return currentData.timeline.map((p, i) => ({
      x: xScale(i, currentData.timeline.length),
      y: yScale(p.total_size_bytes, maxSize),
      value: p.total_size_bytes
    }));
  });

  let timelineHitRatePoints = $derived.by(() => {
    const currentData = data;
    if (!currentData || currentData.timeline.length === 0) return [];
    return currentData.timeline.map((p, i) => ({
      x: xScale(i, currentData.timeline.length),
      y: yScaleHitRate(p.avg_hit_rate),
      value: p.avg_hit_rate
    }));
  });

  let timelineSizePath = $derived.by(() => {
    const points = timelineSizePoints;
    if (points.length === 0) return '';
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  });

  let timelineHitRatePath = $derived.by(() => {
    const points = timelineHitRatePoints;
    if (points.length === 0) return '';
    return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  });

  // ── Index table helpers ──────────────────────────────────────────────────────
  let sortedItems = $derived.by(() => {
    const currentData = data;
    if (!currentData) return [];
    return [...currentData.items].sort((a, b) => b.latest_size_bytes - a.latest_size_bytes);
  });

  let paginatedItems = $derived.by(() => {
    return sortedItems.slice(tablePageOffset, tablePageOffset + tablePageLimit);
  });

  let totalTablePages = $derived.by(() => {
    return Math.ceil(sortedItems.length / tablePageLimit);
  });

  function changeTablePage(delta: number) {
    const next = tablePageOffset + delta * tablePageLimit;
    if (next < 0 || next >= sortedItems.length) return;
    tablePageOffset = next;
  }

  function badgeClass(type: string): string {
    const lower = type.toLowerCase();
    if (lower.includes('btree')) return 'bg-blue-100 text-blue-700 border-blue-200';
    if (lower.includes('hash')) return 'bg-amber-100 text-amber-700 border-amber-200';
    if (lower.includes('gin')) return 'bg-purple-100 text-purple-700 border-purple-200';
    if (lower.includes('gist')) return 'bg-pink-100 text-pink-700 border-pink-200';
    return 'bg-surface-variant text-on-surface-variant border-outline-variant';
  }
</script>

<!-- ── Top Bar ─────────────────────────────────────────────────────────────── -->
<header class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16">
  <div class="flex items-center gap-3">
    <span class="material-symbols-outlined text-primary">speed</span>
    <h1 class="font-headline-md text-headline-md text-on-background m-0">Analytics</h1>
    <span class="font-label-caps text-[10px] text-on-surface-variant">/ Index</span>
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
        Connect a database from the Servers page to view analytics.
      </p>
    </div>
  {:else}
    <!-- Database selector -->
    <div class="mb-6 flex flex-wrap items-center gap-3">
      <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Database</span>
      {#each databases as db}
        <button
          onclick={() => selectDatabase(db, true)}
          class="cursor-pointer rounded-lg px-3 py-1.5 text-xs font-bold transition-all {selectedDb?.id === db.id ? 'bg-primary text-on-primary' : 'border border-outline-variant bg-surface-container text-on-surface-variant hover:bg-surface-variant'}"
        >
          {db.name}
        </button>
      {/each}
    </div>

    <!-- Controls -->
    <section class="mb-6 rounded-lg border border-outline-variant bg-surface-container p-4">
      <div class="flex flex-wrap items-end gap-4">
        <!-- Presets -->
        <div class="flex flex-col gap-2">
          <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Range</span>
          <div class="flex rounded-lg border border-outline-variant overflow-hidden">
            {#each presets as p}
              <button
                onclick={() => { preset = p.value; applyFilters(); }}
                class="px-3 py-1.5 text-xs font-bold transition-colors {preset === p.value ? 'bg-primary text-on-primary' : 'bg-surface-container text-on-surface-variant hover:bg-surface-variant'}"
              >
                {p.label}
              </button>
            {/each}
          </div>
        </div>

        <!-- Custom dates -->
        {#if preset === 'custom'}
          <div class="flex flex-col gap-2">
            <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Start</span>
            <input
              type="datetime-local"
              bind:value={startDate}
              class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
            />
          </div>
          <div class="flex flex-col gap-2">
            <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">End</span>
            <input
              type="datetime-local"
              bind:value={endDate}
              class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
            />
          </div>
          <button
            onclick={applyFilters}
            class="px-4 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-bold hover:bg-primary/90 cursor-pointer"
          >
            Apply
          </button>
        {/if}

        <!-- Table filter -->
        <div class="flex flex-col gap-2 min-w-[16rem] relative">
          <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Tables</span>
          <button
            onclick={() => tableDropdownOpen = !tableDropdownOpen}
            class="w-full flex items-center justify-between px-3 py-1.5 bg-surface-container-high border border-outline-variant rounded-lg text-xs text-on-surface hover:border-primary/40 cursor-pointer"
          >
            <span>
              {#if selectedTableIds.length === 0}
                All tables
              {:else if selectedTableIds.length === 1}
                1 table selected
              {:else}
                {selectedTableIds.length} tables selected
              {/if}
            </span>
            <span class="material-symbols-outlined text-[14px] transition-transform duration-200" style="transform: rotate({tableDropdownOpen ? 180 : 0}deg)">expand_more</span>
          </button>

          {#if tableDropdownOpen}
            <div class="absolute top-full left-0 right-0 mt-1 z-50 rounded-lg border border-outline-variant bg-surface-container shadow-lg overflow-hidden">
              <div class="p-2 border-b border-outline-variant">
                <input
                  type="text"
                  bind:value={tableSearchTerm}
                  placeholder="Search tables..."
                  class="w-full bg-surface-container-high border border-outline-variant rounded px-2 py-1 text-xs text-on-surface focus:border-primary focus:outline-none"
                />
              </div>
              <div class="max-h-48 overflow-y-auto p-1">
                {#each searchedTables as table}
                  <label class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-surface-variant text-xs text-on-surface">
                    <input
                      type="checkbox"
                      checked={selectedTableIds.includes(table.id)}
                      onchange={() => { toggleTable(table.id); applyFilters(); }}
                      class="accent-primary w-3.5 h-3.5"
                    />
                    <span class="truncate">{displayTableName(table)}</span>
                  </label>
                {:else}
                  <p class="px-2 py-1.5 text-xs text-on-surface-variant">No tables found</p>
                {/each}
              </div>
              {#if selectedTableIds.length > 0}
                <div class="p-2 border-t border-outline-variant">
                  <button
                    onclick={() => { selectedTableIds = []; applyFilters(); }}
                    class="text-[10px] text-error hover:underline cursor-pointer"
                  >
                    Clear selection
                  </button>
                </div>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Index filter -->
        <div class="flex flex-col gap-2 min-w-[16rem] relative">
          <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Indexes</span>
          <button
            onclick={() => indexDropdownOpen = !indexDropdownOpen}
            class="w-full flex items-center justify-between px-3 py-1.5 bg-surface-container-high border border-outline-variant rounded-lg text-xs text-on-surface hover:border-primary/40 cursor-pointer"
          >
            <span>
              {#if selectedIndexIds.length === 0}
                All indexes
              {:else if selectedIndexIds.length === 1}
                1 index selected
              {:else}
                {selectedIndexIds.length} indexes selected
              {/if}
            </span>
            <span class="material-symbols-outlined text-[14px] transition-transform duration-200" style="transform: rotate({indexDropdownOpen ? 180 : 0}deg)">expand_more</span>
          </button>

          {#if indexDropdownOpen}
            <div class="absolute top-full left-0 right-0 mt-1 z-50 rounded-lg border border-outline-variant bg-surface-container shadow-lg overflow-hidden">
              <div class="p-2 border-b border-outline-variant">
                <input
                  type="text"
                  bind:value={indexSearchTerm}
                  placeholder="Search indexes..."
                  class="w-full bg-surface-container-high border border-outline-variant rounded px-2 py-1 text-xs text-on-surface focus:border-primary focus:outline-none"
                />
              </div>
              <div class="max-h-48 overflow-y-auto p-1">
                {#each searchedIndexes as idx}
                  <label class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-surface-variant text-xs text-on-surface">
                    <input
                      type="checkbox"
                      checked={selectedIndexIds.includes(idx.id)}
                      onchange={() => { toggleIndex(idx.id); applyFilters(); }}
                      class="accent-primary w-3.5 h-3.5"
                    />
                    <span class="truncate">{idx.index_name} <span class="text-on-surface-variant">({displayTableName({ schema_name: idx.schema_name, table_name: idx.table_name })})</span></span>
                  </label>
                {:else}
                  <p class="px-2 py-1.5 text-xs text-on-surface-variant">No indexes found</p>
                {/each}
              </div>
              {#if selectedIndexIds.length > 0}
                <div class="p-2 border-t border-outline-variant">
                  <button
                    onclick={() => { selectedIndexIds = []; applyFilters(); }}
                    class="text-[10px] text-error hover:underline cursor-pointer"
                  >
                    Clear selection
                  </button>
                </div>
              {/if}
            </div>
          {/if}
        </div>

        <!-- Search -->
        <div class="flex flex-col gap-2 min-w-[16rem]">
          <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Search</span>
          <div class="flex gap-2">
            <input
              type="text"
              bind:value={searchTerm}
              placeholder="Index, table or schema..."
              class="flex-1 bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
              onkeydown={(e: KeyboardEvent) => { if (e.key === 'Enter') applyFilters(); }}
            />
            <button
              onclick={applyFilters}
              class="px-3 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-bold hover:bg-primary/90 cursor-pointer"
            >
              Search
            </button>
          </div>
        </div>
      </div>

      <!-- Selected chips -->
      {#if selectedTableIds.length > 0 || selectedIndexIds.length > 0}
        <div class="mt-3 flex flex-wrap items-center gap-2">
          {#each selectedTableIds as tableId}
            {@const table = data?.tables.find((t) => t.id === tableId)}
            {#if table}
              <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold border border-outline-variant bg-surface-container text-on-surface">
                {displayTableName(table)}
                <button onclick={() => { toggleTable(table.id); applyFilters(); }} class="material-symbols-outlined text-[12px] hover:opacity-70 cursor-pointer">close</button>
              </span>
            {/if}
          {/each}
          {#each selectedIndexIds as indexId}
            {@const idx = data?.indexes.find((i) => i.id === indexId)}
            {#if idx}
              <span class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold border border-primary/30 bg-primary/10 text-primary">
                {idx.index_name}
                <button onclick={() => { toggleIndex(idx.id); applyFilters(); }} class="material-symbols-outlined text-[12px] hover:opacity-70 cursor-pointer">close</button>
              </span>
            {/if}
          {/each}
        </div>
      {/if}
    </section>

    <!-- KPIs -->
    {#if data}
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        <div class="rounded-lg border border-outline-variant bg-surface-container p-4">
          <p class="text-[10px] uppercase tracking-widest text-on-surface-variant mb-1">Total Indexes</p>
          <p class="font-headline-md text-headline-md font-bold text-on-surface">{formatNumber(data.kpis.total_indexes)}</p>
        </div>
        <div class="rounded-lg border border-outline-variant bg-surface-container p-4">
          <p class="text-[10px] uppercase tracking-widest text-on-surface-variant mb-1">Total Size</p>
          <p class="font-headline-md text-headline-md font-bold text-on-surface">{formatBytes(data.kpis.total_size_bytes)}</p>
        </div>
        <div class="rounded-lg border border-outline-variant bg-surface-container p-4">
          <p class="text-[10px] uppercase tracking-widest text-on-surface-variant mb-1">Avg Hit Rate</p>
          <p class="font-headline-md text-headline-md font-bold text-on-surface">{formatPercent(data.kpis.avg_hit_rate)}</p>
        </div>
        <div class="rounded-lg border border-outline-variant bg-surface-container p-4">
          <p class="text-[10px] uppercase tracking-widest text-on-surface-variant mb-1">Avg Scans</p>
          <p class="font-headline-md text-headline-md font-bold text-on-surface">{formatNumber(data.kpis.avg_scan_qt)}</p>
        </div>
        <div class="rounded-lg border border-outline-variant bg-surface-container p-4">
          <p class="text-[10px] uppercase tracking-widest text-on-surface-variant mb-1">Unused Indexes</p>
          <p class="font-headline-md text-headline-md font-bold text-on-surface">{formatNumber(data.kpis.unused_indexes)}</p>
        </div>
        <div class="rounded-lg border border-outline-variant bg-surface-container p-4">
          <p class="text-[10px] uppercase tracking-widest text-on-surface-variant mb-1">Unique / Primary</p>
          <p class="font-headline-md text-headline-md font-bold text-on-surface">{data.kpis.unique_indexes} / {data.kpis.primary_indexes}</p>
        </div>
      </div>
    {/if}

    <!-- Timeline chart -->
    <section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden mb-6">
      <div class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-sm text-primary">show_chart</span>
          <h2 class="m-0 font-headline-md text-headline-md">Total index size & hit rate</h2>
        </div>
        <div class="relative">
          <button
            onclick={() => chartHelpOpen = !chartHelpOpen}
            onmouseenter={() => chartHelpOpen = true}
            onmouseleave={() => chartHelpOpen = false}
            class="flex items-center justify-center w-6 h-6 rounded-full border border-outline-variant text-on-surface-variant hover:text-primary hover:border-primary/40 transition-colors cursor-pointer"
            aria-label="Chart explanation"
          >
            <span class="material-symbols-outlined text-[14px]">help</span>
          </button>
          {#if chartHelpOpen}
            <div class="absolute right-0 top-full mt-2 w-72 z-50 rounded-lg border border-outline-variant bg-surface-container-high shadow-lg p-3 text-xs text-on-surface">
              <p class="font-bold mb-1">What this chart shows</p>
              <p class="text-on-surface-variant mb-2">
                This chart combines three dimensions over the selected time range:
              </p>
              <ul class="space-y-1.5 text-on-surface-variant list-disc pl-4">
                <li><span class="font-medium text-primary">Solid line</span> — total size of all selected indexes (left axis).</li>
                <li><span class="font-medium text-amber-500">Dashed line</span> — average buffer hit rate across selected indexes (right axis, 0–100%).</li>
                <li><span class="font-medium text-on-surface">Hover</span> — also shows total index scans for that point in time.</li>
              </ul>
            </div>
          {/if}
        </div>
      </div>

      <div class="relative p-4" bind:clientWidth={timelineChartWidth}>
        {#if loading}
          <div class="flex items-center justify-center py-24">
            <svg class="h-8 w-8 animate-spin text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
        {:else if !data || data.timeline.length === 0}
          <div class="flex flex-col items-center justify-center py-24 text-on-surface-variant">
            <span class="material-symbols-outlined text-[40px] mb-3">insert_chart</span>
            <p class="text-sm">No index data available for the selected period.</p>
          </div>
        {:else}
          <svg
            role="img"
            aria-label="Index analytics timeline chart"
            width="100%"
            height={timelineChartHeight}
            class="overflow-visible"
            onmousemove={handleTimelineMouseMove}
            onmouseleave={handleTimelineMouseLeave}
          >
            <!-- Grid lines -->
            {#each [0, 0.25, 0.5, 0.75, 1] as tick}
              {@const y = padding.top + tick * (timelineChartHeight - padding.top - padding.bottom)}
              <line x1={padding.left} y1={y} x2={timelineChartWidth - padding.right} y2={y} stroke="currentColor" stroke-opacity="0.1" />
            {/each}

            <!-- X axis labels -->
            {#if data.timeline.length > 0}
              {#each [0, Math.floor((data.timeline.length - 1) / 2), data.timeline.length - 1] as idx}
                {@const x = xScale(idx, data.timeline.length)}
                <text x={x} y={timelineChartHeight - 8} text-anchor="middle" class="text-[10px] fill-on-surface-variant">{formatChartDate(data.timeline[idx].collected_at)}</text>
              {/each}
            {/if}

            <!-- Left axis: size -->
            {#if timelineSizePoints.length > 0}
              {@const maxSize = Math.max(...data.timeline.map((p) => p.total_size_bytes), 1)}
              <text x={padding.left - 8} y={padding.top + 4} text-anchor="end" class="text-[10px] fill-on-surface-variant">{formatBytes(maxSize)}</text>
              <text x={padding.left - 8} y={timelineChartHeight - padding.bottom} text-anchor="end" class="text-[10px] fill-on-surface-variant">0 B</text>
            {/if}

            <!-- Right axis: hit rate -->
            <text x={timelineChartWidth - padding.right + 8} y={padding.top + 4} text-anchor="start" class="text-[10px] fill-amber-500">100%</text>
            <text x={timelineChartWidth - padding.right + 8} y={timelineChartHeight - padding.bottom} text-anchor="start" class="text-[10px] fill-amber-500">0%</text>

            <!-- Size line -->
            <path d={timelineSizePath} fill="none" stroke={colors[0]} stroke-width="2" />
            {#each timelineSizePoints as pt}
              <circle cx={pt.x} cy={pt.y} r="3" fill={colors[0]} />
            {/each}

            <!-- Hit rate line -->
            <path d={timelineHitRatePath} fill="none" stroke="#f59e0b" stroke-width="2" stroke-dasharray="4 4" />
            {#each timelineHitRatePoints as pt}
              <circle cx={pt.x} cy={pt.y} r="3" fill="#f59e0b" />
            {/each}

            <!-- Hover line -->
            {#if timelineHoverIndex !== null}
              {@const x = xScale(timelineHoverIndex, data.timeline.length)}
              <line x1={x} y1={padding.top} x2={x} y2={timelineChartHeight - padding.bottom} stroke="currentColor" stroke-opacity="0.3" stroke-dasharray="4 4" />
            {/if}
          </svg>

          <!-- Tooltip -->
          {#if timelineHoverIndex !== null}
            {@const point = data.timeline[timelineHoverIndex]}
            <div class="pointer-events-none absolute right-4 top-4 z-10 rounded-lg border border-outline-variant bg-surface-container-high p-3 text-xs shadow-lg">
              <p class="font-bold text-on-surface mb-1">{formatChartDate(point.collected_at)}</p>
              <p class="text-on-surface-variant">Total size: <span class="font-bold text-on-surface">{formatBytes(point.total_size_bytes)}</span></p>
              <p class="text-on-surface-variant">Total scans: <span class="font-bold text-on-surface">{formatNumber(point.total_scans)}</span></p>
              <p class="text-on-surface-variant">Avg hit rate: <span class="font-bold text-on-surface">{formatPercent(point.avg_hit_rate)}</span></p>
            </div>
          {/if}
        {/if}
      </div>
    </section>

    <!-- Index table -->
    <section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden">
      <div class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-sm text-primary">list</span>
          <h2 class="m-0 font-headline-md text-headline-md">Indexes</h2>
        </div>
        <span class="text-xs text-on-surface-variant">{sortedItems.length} indexes</span>
      </div>

      <div class="overflow-x-auto">
        {#if loading}
          <div class="flex items-center justify-center py-24">
            <svg class="h-8 w-8 animate-spin text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
        {:else if sortedItems.length === 0}
          <div class="flex flex-col items-center justify-center py-24 text-on-surface-variant">
            <span class="material-symbols-outlined text-[40px] mb-3">data_array</span>
            <p class="text-sm">No indexes match the selected filters.</p>
          </div>
        {:else}
          <table class="w-full text-left text-sm">
            <thead class="bg-surface-container-high text-on-surface-variant text-xs uppercase">
              <tr>
                <th class="px-4 py-3 font-semibold">Index</th>
                <th class="px-4 py-3 font-semibold">Table</th>
                <th class="px-4 py-3 font-semibold">Type</th>
                <th class="px-4 py-3 font-semibold">Size</th>
                <th class="px-4 py-3 font-semibold">Scans</th>
                <th class="px-4 py-3 font-semibold">Hit Rate</th>
                <th class="px-4 py-3 font-semibold">Attributes</th>
                <th class="px-4 py-3 font-semibold"></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-outline-variant">
              {#each paginatedItems as item}
                <tr class="hover:bg-surface-variant/50 transition-colors">
                  <td class="px-4 py-3 text-on-surface font-medium">{item.index_name}</td>
                  <td class="px-4 py-3 text-on-surface-variant">{displayTableName({ schema_name: item.schema_name, table_name: item.table_name })}</td>
                  <td class="px-4 py-3">
                    <span class="inline-flex px-2 py-0.5 rounded text-[10px] font-bold border {badgeClass(item.index_type)}">
                      {item.index_type}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-on-surface font-medium">{formatBytes(item.latest_size_bytes)}</td>
                  <td class="px-4 py-3 text-on-surface">{formatNumber(item.latest_scan_qt)}</td>
                  <td class="px-4 py-3 text-on-surface">{formatPercent(item.hit_rate)}</td>
                  <td class="px-4 py-3">
                    <div class="flex gap-1">
                      {#if item.is_primary}
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-primary/10 text-primary border border-primary/20">PK</span>
                      {/if}
                      {#if item.is_unique}
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-secondary/10 text-secondary border border-secondary/20">UQ</span>
                      {/if}
                      {#if !item.latest_scan_qt}
                        <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-error/10 text-error border border-error/20">unused</span>
                      {/if}
                    </div>
                  </td>
                  <td class="px-4 py-3">
                    <button
                      onclick={() => expandedIndex = expandedIndex === item.index_id ? null : item.index_id}
                      class="text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                    >
                      <span class="material-symbols-outlined text-[18px]">{expandedIndex === item.index_id ? 'expand_less' : 'expand_more'}</span>
                    </button>
                  </td>
                </tr>
                {#if expandedIndex === item.index_id}
                  <tr class="bg-surface-container-low">
                    <td colspan="8" class="px-4 py-4">
                      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs mb-4">
                        <div>
                          <p class="text-on-surface-variant mb-0.5">First seen</p>
                          <p class="text-on-surface font-medium">{item.first_seen ? new Date(item.first_seen).toLocaleString() : '--'}</p>
                        </div>
                        <div>
                          <p class="text-on-surface-variant mb-0.5">Last seen</p>
                          <p class="text-on-surface font-medium">{item.last_seen ? new Date(item.last_seen).toLocaleString() : '--'}</p>
                        </div>
                        <div>
                          <p class="text-on-surface-variant mb-0.5">Tuples read</p>
                          <p class="text-on-surface font-medium">{formatNumber(item.latest_tup_read_qt)}</p>
                        </div>
                        <div>
                          <p class="text-on-surface-variant mb-0.5">Tuples fetched</p>
                          <p class="text-on-surface font-medium">{formatNumber(item.latest_tup_fetch_qt)}</p>
                        </div>
                      </div>
                      {#if item.history.length > 1}
                        {@const maxSize = Math.max(...item.history.map((p) => p.size_bytes), 1)}
                        {@const histPadding = { top: 8, right: 8, bottom: 20, left: 40 }}
                        {@const chartW = 600}
                        {@const chartH = 128}
                        {@const usableW = chartW - histPadding.left - histPadding.right}
                        {@const usableH = chartH - histPadding.top - histPadding.bottom}
                        <div class="h-32 w-full">
                          <svg width="100%" height="100%" class="overflow-visible">
                            {#each item.history as point, i}
                              {@const hx = histPadding.left + (item.history.length <= 1 ? 0 : (i / (item.history.length - 1)) * usableW)}
                              {@const hy = histPadding.top + usableH - ((point.size_bytes / maxSize) * usableH)}
                              <circle cx="{hx}" cy="{hy}" r="2" fill={colors[0]} />
                              {#if i > 0}
                                {@const prev = item.history[i - 1]}
                                {@const px = histPadding.left + (item.history.length <= 1 ? 0 : ((i - 1) / (item.history.length - 1)) * usableW)}
                                {@const py = histPadding.top + usableH - ((prev.size_bytes / maxSize) * usableH)}
                                <line x1={px} y1={py} x2={hx} y2={hy} stroke={colors[0]} stroke-width="1.5" />
                              {/if}
                            {/each}
                            <text x={histPadding.left - 8} y={histPadding.top + 4} text-anchor="end" class="text-[9px] fill-on-surface-variant">{formatBytes(maxSize)}</text>
                            <text x={histPadding.left - 8} y={chartH - histPadding.bottom} text-anchor="end" class="text-[9px] fill-on-surface-variant">0</text>
                          </svg>
                        </div>
                      {/if}
                    </td>
                  </tr>
                {/if}
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      {#if sortedItems.length > tablePageLimit}
        <div class="flex items-center justify-between border-t border-outline-variant bg-surface-container-low px-4 py-3">
          <span class="text-xs text-on-surface-variant">
            Showing {tablePageOffset + 1}-{Math.min(tablePageOffset + tablePageLimit, sortedItems.length)} of {sortedItems.length}
          </span>
          <div class="flex items-center gap-2">
            <button
              onclick={() => changeTablePage(-1)}
              disabled={tablePageOffset === 0}
              class="px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-xs font-bold text-on-surface hover:border-primary/40 hover:text-primary disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              Previous
            </button>
            <button
              onclick={() => changeTablePage(1)}
              disabled={tablePageOffset + tablePageLimit >= sortedItems.length}
              class="px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-xs font-bold text-on-surface hover:border-primary/40 hover:text-primary disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      {/if}
    </section>
  {/if}
</div>
