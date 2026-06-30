<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
  import { listDatabases, getAnalyticsData, formatBytes } from '$lib/api';
  import type { DatabaseListItem, AnalyticsDataResponse, AnalyticsPreset, AnalyticsTableSizePoint, AnalyticsDatabaseSizePoint } from '$lib/api';

  // ── State ────────────────────────────────────────────────────────────────────
  let databases = $state<DatabaseListItem[]>([]);
  let selectedDb = $state<DatabaseListItem | null>(null);
  let data = $state<AnalyticsDataResponse | null>(null);
  let loading = $state(true);
  let error = $state('');

  let preset = $state<AnalyticsPreset>('1w');
  let startDate = $state('');
  let endDate = $state('');
  let selectedTableIds = $state<number[]>([]);
  let hoverIndex = $state<number | null>(null);
  let tableSearch = $state('');
  let tableDropdownOpen = $state(false);
  let showDatabase = $state(true);
  let logScale = $state(true);

  const presets: { label: string; value: AnalyticsPreset }[] = [
    { label: '1D', value: '1d' },
    { label: '3D', value: '3d' },
    { label: '1W', value: '1w' },
    { label: '2W', value: '2w' },
    { label: '1M', value: '1m' },
    { label: 'Custom', value: 'custom' },
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

  function allTimestamps(
    dbHistory: AnalyticsDatabaseSizePoint[],
    tableHistory: AnalyticsTableSizePoint[],
    selectedTableIds: number[],
    showDatabase: boolean
  ): Date[] {
    const set = new Set<number>();
    if (showDatabase) {
      dbHistory.forEach((p) => set.add(new Date(p.collected_at).getTime()));
    }
    if (selectedTableIds.length > 0) {
      const ids = new Set(selectedTableIds);
      tableHistory
        .filter((p) => ids.has(p.table_id))
        .forEach((p) => set.add(new Date(p.collected_at).getTime()));
    }
    return Array.from(set).sort((a, b) => a - b).map((t) => new Date(t));
  }

  function seriesForTable(tableId: number, tableHistory: AnalyticsTableSizePoint[], timestamps: Date[]): number[] {
    const map = new Map<number, number>();
    tableHistory
      .filter((p) => p.table_id === tableId)
      .forEach((p) => map.set(new Date(p.collected_at).getTime(), p.size_bytes));
    let last: number | null = null;
    return timestamps.map((t) => {
      const value = map.get(t.getTime());
      if (value !== undefined) last = value;
      return last ?? 0;
    });
  }

  function dbSeries(dbHistory: AnalyticsDatabaseSizePoint[], timestamps: Date[]): number[] {
    const map = new Map<number, number>();
    dbHistory.forEach((p) => map.set(new Date(p.collected_at).getTime(), p.size_bytes));
    let last: number | null = null;
    return timestamps.map((t) => {
      const value = map.get(t.getTime());
      if (value !== undefined) last = value;
      return last ?? 0;
    });
  }

  function formatChartDate(date: Date): string {
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function generateYTicks(): { value: number; label: string; y: number }[] {
    const usableHeight = chartHeight - padding.top - padding.bottom;
    if (!logScale) {
      return [0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const value = maxBytesValue * (1 - tick);
        return {
          value,
          label: formatBytes(value),
          y: padding.top + tick * usableHeight,
        };
      });
    }

    const maxLog = Math.log10(Math.max(1, maxBytesValue));
    const minLog = Math.log10(Math.max(1, minBytesValue));
    const logRange = Math.max(1, maxLog - minLog);

    const ticks: { value: number; label: string; y: number }[] = [];
    const startPow = Math.ceil(minLog);
    const endPow = Math.floor(maxLog);

    for (let p = startPow; p <= endPow; p++) {
      const value = Math.pow(10, p);
      if (value < minBytesValue || value > maxBytesValue) continue;
      const ratio = (Math.log10(value) - minLog) / logRange;
      ticks.push({ value, label: formatBytes(value), y: padding.top + (1 - ratio) * usableHeight });
    }

    // Fallback if no powers of 10 fit (e.g., narrow range)
    if (ticks.length === 0) {
      [0, 0.25, 0.5, 0.75, 1].forEach((tick) => {
        const value = maxBytesValue * (1 - tick);
        ticks.push({
          value,
          label: formatBytes(value),
          y: padding.top + tick * usableHeight,
        });
      });
    }

    return ticks;
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
    try {
      const options: Parameters<typeof getAnalyticsData>[1] = {
        tableIds: selectedTableIds.length > 0 ? selectedTableIds : undefined,
      };
      if (preset === 'custom') {
        options.startDate = startDate ? fromInputDate(startDate) : undefined;
        options.endDate = endDate ? fromInputDate(endDate) : undefined;
      } else {
        options.preset = preset;
      }
      data = await getAnalyticsData(database.id, options);
      const existingIds = new Set(data.tables.map((t) => t.id));
      selectedTableIds = selectedTableIds.filter((id) => existingIds.has(id));
    } catch (err: any) {
      if (err.message?.includes('401')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
        return;
      }
      error = err.message || 'Failed to load analytics data.';
      data = null;
    } finally {
      loading = false;
    }
  }

  async function selectDatabase(database: DatabaseListItem, replace = false) {
    if (replace) {
      await goto(`/analytics/${database.id}/data`, { replaceState: true });
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
        await goto(`/analytics/${db.id}/data`, { replaceState: true });
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

  function toggleTable(id: number) {
    if (selectedTableIds.includes(id)) {
      selectedTableIds = selectedTableIds.filter((x) => x !== id);
    } else {
      selectedTableIds = [...selectedTableIds, id];
    }
  }

  onMount(() => load());

  // ── Chart computation ────────────────────────────────────────────────────────
  let timestamps = $derived(
    data ? allTimestamps(data.database_size_history, data.table_size_history, selectedTableIds, showDatabase) : []
  );

  let dbValues = $derived(data ? dbSeries(data.database_size_history, timestamps) : []);
  let tableValues = $derived.by(() => {
    const currentData = data;
    if (!currentData) return [];
    return selectedTableIds.map((id, i) => ({
      id,
      color: colors[(i + 1) % colors.length],
      values: seriesForTable(id, currentData.table_size_history, timestamps)
    }));
  });

  let visibleDbValues = $derived(showDatabase ? dbValues : []);
  let visibleTableValues = $derived(tableValues);

  let maxBytesValue = $derived.by(() => {
    if (!data || timestamps.length === 0) return 1;
    let max = 0;
    visibleDbValues.forEach((v) => max = Math.max(max, v));
    visibleTableValues.forEach((tv) => tv.values.forEach((v) => max = Math.max(max, v)));
    return max || 1;
  });

  let minBytesValue = $derived.by(() => {
    if (!data || timestamps.length === 0) return 1;
    let min = Infinity;
    visibleDbValues.forEach((v) => { if (v > 0) min = Math.min(min, v); });
    visibleTableValues.forEach((tv) => tv.values.forEach((v) => { if (v > 0) min = Math.min(min, v); }));
    return isFinite(min) ? min : 1;
  });

  let chartWidth = $state(0);
  const chartHeight = 320;
  const padding = { top: 20, right: 24, bottom: 48, left: 72 };

  function xScale(index: number): number {
    if (timestamps.length <= 1) return padding.left;
    const usableWidth = chartWidth - padding.left - padding.right;
    return padding.left + (index / (timestamps.length - 1)) * usableWidth;
  }

  function yScale(value: number): number {
    const usableHeight = chartHeight - padding.top - padding.bottom;
    let y: number;
    if (logScale) {
      const maxLog = Math.log10(Math.max(1, maxBytesValue));
      const minLog = Math.log10(Math.max(1, minBytesValue));
      const logRange = Math.max(1, maxLog - minLog);
      const v = Math.max(1, value);
      y = padding.top + usableHeight - ((Math.log10(v) - minLog) / logRange) * usableHeight;
    } else {
      y = padding.top + usableHeight - (value / maxBytesValue) * usableHeight;
    }
    return Math.max(padding.top, Math.min(padding.top + usableHeight, y));
  }

  function pathForSeries(values: number[]): string {
    let d = '';
    values.forEach((value, i) => {
      const x = xScale(i);
      const y = yScale(value);
      d += d ? ` L ${x} ${y}` : `M ${x} ${y}`;
    });
    return d;
  }

  function circlePoints(values: number[]): { x: number; y: number; value: number }[] {
    return values.map((value, i) => ({ x: xScale(i), y: yScale(value), value }));
  }

  let tableMap = $derived.by(() => {
    const currentData = data;
    if (!currentData) return new Map<number, { schema_name: string; table_name: string }>();
    return new Map(currentData.tables.map((t) => [t.id, { schema_name: t.schema_name, table_name: t.name }]));
  });

  let tooltip = $derived.by(() => {
    if (hoverIndex === null || !data || timestamps.length === 0) return null;
    const idx = hoverIndex;
    const ts = timestamps[idx];
    const dbValue = dbValues[idx];
    const tables: { schema_name: string; table_name: string; size_bytes: number }[] = [];

    tableValues.forEach((tv) => {
      const value = tv.values[idx];
      const meta = tableMap.get(tv.id);
      if (meta) {
        tables.push({ ...meta, size_bytes: value });
      }
    });

    return {
      ts,
      database: showDatabase ? { collected_at: ts.toISOString(), size_bytes: dbValue } : null,
      tables,
    };
  });

  function handleChartMouseMove(event: MouseEvent) {
    if (timestamps.length === 0) return;
    const svg = event.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const usableWidth = chartWidth - padding.left - padding.right;
    const ratio = Math.max(0, Math.min(1, (x - padding.left) / usableWidth));
    const index = Math.round(ratio * (timestamps.length - 1));
    hoverIndex = Math.max(0, Math.min(timestamps.length - 1, index));
  }

  function handleChartMouseLeave() {
    hoverIndex = null;
  }

  let filteredTables = $derived.by(() => {
    const currentData = data;
    if (!currentData) return [];
    const term = tableSearch.trim().toLowerCase();
    return currentData.tables.filter((t) => t.name.toLowerCase().includes(term));
  });
</script>

<!-- ── Top Bar ─────────────────────────────────────────────────────────────── -->
<header class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16">
  <div class="flex items-center gap-3">
    <span class="material-symbols-outlined text-primary">analytics</span>
    <h1 class="font-headline-md text-headline-md text-on-background m-0">Analytics</h1>
    <span class="font-label-caps text-[10px] text-on-surface-variant">/ Data</span>
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
    <!-- Controls -->
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

        <!-- Display options -->
        <div class="flex flex-col gap-2">
          <span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Display</span>
          <div class="flex items-center gap-4">
            <label class="flex items-center gap-1.5 text-xs text-on-surface cursor-pointer">
              <input
                type="checkbox"
                bind:checked={showDatabase}
                class="accent-primary w-3.5 h-3.5"
              />
              Database
            </label>
            <label class="flex items-center gap-1.5 text-xs text-on-surface cursor-pointer">
              <input
                type="checkbox"
                bind:checked={logScale}
                class="accent-primary w-3.5 h-3.5"
              />
              Log scale
            </label>
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
                  bind:value={tableSearch}
                  placeholder="Search tables..."
                  class="w-full bg-surface-container-high border border-outline-variant rounded px-2 py-1 text-xs text-on-surface focus:border-primary focus:outline-none"
                />
              </div>
              <div class="max-h-48 overflow-y-auto p-1">
                {#each filteredTables as table}
                  <label class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-surface-variant text-xs text-on-surface">
                    <input
                      type="checkbox"
                      checked={selectedTableIds.includes(table.id)}
                      onchange={() => { toggleTable(table.id); applyFilters(); }}
                      class="accent-primary w-3.5 h-3.5"
                    />
                    <span class="truncate">{displayTableName(table)}</span>
                  </label>
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
      </div>

      <!-- Selected table chips -->
      {#if selectedTableIds.length > 0}
        <div class="mt-3 flex flex-wrap items-center gap-2">
          {#each selectedTableIds as tableId, i}
            {@const table = data?.tables.find((t) => t.id === tableId)}
            {#if table}
              <span
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold border"
                style="border-color: {colors[(i + 1) % colors.length]}; background-color: {colors[(i + 1) % colors.length]}1A; color: {colors[(i + 1) % colors.length]};"
              >
                {displayTableName(table)}
                <button
                  onclick={() => { toggleTable(table.id); applyFilters(); }}
                  class="material-symbols-outlined text-[12px] hover:opacity-70 cursor-pointer"
                >close</button>
              </span>
            {/if}
          {/each}
        </div>
      {/if}
    </section>

    <!-- Chart -->
    <section class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden">
      <div class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-sm text-primary">show_chart</span>
          <h2 class="m-0 font-headline-md text-headline-md">Size History</h2>
        </div>
        <div class="flex items-center gap-4 text-xs">
          {#if showDatabase}
            <span class="flex items-center gap-1.5">
              <span class="w-3 h-1 rounded bg-current" style="color: {colors[0]}"></span>
              Database
            </span>
          {/if}
          {#each selectedTableIds as tableId, i}
            {@const table = data?.tables.find((t) => t.id === tableId)}
            {#if table}
              <span class="flex items-center gap-1.5">
                <span class="w-3 h-1 rounded bg-current" style="color: {colors[(i + 1) % colors.length]}"></span>
                {displayTableName(table)}
              </span>
            {/if}
          {/each}
        </div>
      </div>

      <div class="p-4" bind:clientWidth={chartWidth}>
        {#if loading}
          <div class="flex items-center justify-center py-24">
            <svg class="h-8 w-8 animate-spin text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
        {:else if !data || timestamps.length === 0}
          <div class="flex flex-col items-center justify-center py-24 text-on-surface-variant">
            <span class="material-symbols-outlined text-[40px] mb-3">insert_chart</span>
            <p class="text-sm">No data available for the selected period.</p>
          </div>
        {:else}
          <svg
            role="img"
            aria-label="Size history chart"
            width="100%"
            height={chartHeight}
            class="overflow-visible"
            onmousemove={handleChartMouseMove}
            onmouseleave={handleChartMouseLeave}
          >
            <!-- Grid lines -->
            {#each generateYTicks() as tick}
              <line x1={padding.left} y1={tick.y} x2={chartWidth - padding.right} y2={tick.y} stroke="currentColor" stroke-opacity="0.1" />
              <text x={padding.left - 8} y={tick.y + 4} text-anchor="end" class="text-[10px] fill-on-surface-variant">{tick.label}</text>
            {/each}

            <!-- X axis labels -->
            {#if timestamps.length > 0}
              {#each [0, Math.floor((timestamps.length - 1) / 2), timestamps.length - 1] as idx}
                {@const x = xScale(idx)}
                <text x={x} y={chartHeight - 16} text-anchor="middle" class="text-[10px] fill-on-surface-variant">{formatChartDate(timestamps[idx])}</text>
              {/each}
            {/if}

            <!-- Database line -->
            {#if showDatabase}
              <path d={pathForSeries(visibleDbValues)} fill="none" stroke={colors[0]} stroke-width="2" />
              {#each circlePoints(visibleDbValues) as pt}
                <circle cx={pt.x} cy={pt.y} r="3" fill={colors[0]} />
              {/each}
            {/if}

            <!-- Table lines -->
            {#each visibleTableValues as tv}
              <path d={pathForSeries(tv.values)} fill="none" stroke={tv.color} stroke-width="2" />
              {#each circlePoints(tv.values) as pt}
                <circle cx={pt.x} cy={pt.y} r="3" fill={tv.color} />
              {/each}
            {/each}

            <!-- Hover line -->
            {#if hoverIndex !== null}
              {@const x = xScale(hoverIndex)}
              <line x1={x} y1={padding.top} x2={x} y2={chartHeight - padding.bottom} stroke="currentColor" stroke-opacity="0.3" stroke-dasharray="4 4" />
            {/if}
          </svg>

          <!-- Tooltip -->
          {#if tooltip}
            <div class="mt-2 rounded-lg border border-outline-variant bg-surface-container-high p-3 text-xs">
              <p class="font-bold text-on-surface mb-1">{formatChartDate(tooltip.ts)}</p>
              {#if tooltip.database}
                <p class="text-on-surface-variant">Database: <span class="font-bold text-on-surface">{formatBytes(tooltip.database.size_bytes)}</span></p>
              {/if}
              {#each tooltip.tables as t}
                <p class="text-on-surface-variant">{displayTableName(t)}: <span class="font-bold text-on-surface">{formatBytes(t.size_bytes)}</span></p>
              {/each}
            </div>
          {/if}
        {/if}
      </div>
    </section>
  {/if}
</div>
