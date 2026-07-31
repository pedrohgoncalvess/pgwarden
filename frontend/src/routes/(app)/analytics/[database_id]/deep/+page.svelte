<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		formatBytes,
		formatNumber,
		getAnalyticsData,
		getDatabaseSchema,
		getDatabaseSchemaHistory,
		getIndexAnalytics,
		getQueryAnalytics,
		getServerMetricsHistory,
		getServiceHealth,
		listDatabases,
		listServers
	} from '$lib/api';
	import type {
		AnalyticsDataResponse,
		AnalyticsTableSizePoint,
		DatabaseListItem,
		DatabaseSchema,
		IndexAnalyticsResponse,
		QueryAnalyticsResponse,
		SchemaHistoryResponse,
		ServerListItem,
		ServerMetricsHistoryResponse
	} from '$lib/api';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';

	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let loading = $state(true);
	let error = $state('');
	let analyticsOnline = $state(false);
	let schema = $state<DatabaseSchema | null>(null);
	let schemaHistory = $state<SchemaHistoryResponse | null>(null);
	let queryData = $state<QueryAnalyticsResponse | null>(null);
	let tableData = $state<AnalyticsDataResponse | null>(null);
	let indexData = $state<IndexAnalyticsResponse | null>(null);
	let serverData = $state<ServerMetricsHistoryResponse | null>(null);

	function localDate(value: Date): string {
		const offset = value.getTimezoneOffset() * 60_000;
		return new Date(value.getTime() - offset).toISOString().slice(0, 16);
	}

	const now = new Date();
	let startDate = $state(localDate(new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)));
	let endDate = $state(localDate(now));

	function toIso(value: string): string | undefined {
		return value ? new Date(value).toISOString() : undefined;
	}

	function eventValue(event: Event): string {
		return (event.currentTarget as HTMLInputElement | HTMLSelectElement).value;
	}

	function formatDate(value: string | null | undefined): string {
		if (!value) return '—';
		const date = new Date(value);
		return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
	}

	function formatPercent(value: number | null | undefined): string {
		return value === null || value === undefined ? '—' : `${value.toFixed(1)}%`;
	}

	function latestByTime<T extends { collected_at: string }>(items: T[]): T | null {
		return items.reduce<T | null>((latest, item) => {
			return !latest || new Date(item.collected_at) > new Date(latest.collected_at) ? item : latest;
		}, null);
	}

	function hasData(items: unknown[] | undefined): boolean {
		return Boolean(items?.length);
	}

	function databaseHref(databaseId: string): string {
		return `/analytics/${databaseId}/deep`;
	}

	async function selectDatabase(databaseId: string) {
		if (databaseId !== selectedDb?.id) await goto(databaseHref(databaseId));
	}

	async function load() {
		loading = true;
		error = '';
		queryData = null;
		tableData = null;
		indexData = null;
		serverData = null;
		try {
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			const database =
				databases.find((item) => item.id === $page.params.database_id) ?? databases[0];
			if (!database) return;
			if (database.id !== $page.params.database_id) {
				await goto(databaseHref(database.id), { replaceState: true });
				return;
			}
			selectedDb = database;
			selectedDatabaseId.set(database.id);
			selectedServerId.set(database.server_id);

			const [healthResult, schemaResult, historyResult] = await Promise.allSettled([
				getServiceHealth(),
				getDatabaseSchema(database.id),
				getDatabaseSchemaHistory(database.id, undefined, 12)
			]);
			if (schemaResult.status === 'fulfilled') schema = schemaResult.value;
			if (historyResult.status === 'fulfilled') schemaHistory = historyResult.value;
			if (schemaResult.status === 'rejected' && historyResult.status === 'rejected') {
				error = 'The current schema could not be loaded. Try refreshing Time travel.';
			}

			if (healthResult.status !== 'fulfilled') {
				return;
			}
			analyticsOnline = healthResult.value.services.analytics.status === 'healthy';
			if (!analyticsOnline) {
				return;
			}

			const range = { startDate: toIso(startDate), endDate: toIso(endDate) };
			const results = await Promise.allSettled([
				getQueryAnalytics(database.id, { ...range, limit: 8, orderBy: 'total_duration' }),
				getAnalyticsData(database.id, range),
				getIndexAnalytics(database.id, range),
				getServerMetricsHistory(database.id, range)
			]);
			if (results[0].status === 'fulfilled') queryData = results[0].value;
			if (results[1].status === 'fulfilled') tableData = results[1].value;
			if (results[2].status === 'fulfilled') indexData = results[2].value;
			if (results[3].status === 'fulfilled') serverData = results[3].value;
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load Time travel.';
		} finally {
			loading = false;
		}
	}

	onMount(() => {
		void load();
	});

	function setRange(days: number) {
		endDate = localDate(new Date());
		startDate = localDate(new Date(Date.now() - days * 24 * 60 * 60 * 1000));
		void load();
	}

	let latestServer = $derived(latestByTime(serverData?.items ?? []));
	let latestDatabase = $derived(latestByTime(tableData?.database_size_history ?? []));
	let tableSummary = $derived.by(() => {
		const latest = new Map<number, AnalyticsTableSizePoint>();
		for (const point of tableData?.table_size_history ?? []) {
			const prior = latest.get(point.table_id);
			if (!prior || new Date(point.collected_at) > new Date(prior.collected_at))
				latest.set(point.table_id, point);
		}
		return Array.from(latest.values()).sort((a, b) => b.size_bytes - a.size_bytes);
	});
	let latestSchemaEvents = $derived(schemaHistory?.items.slice(0, 6) ?? []);
</script>

<header
	class="fixed top-0 right-0 z-40 flex h-16 w-[calc(100%-16rem)] items-center justify-between border-b border-outline-variant bg-surface-dim px-container-padding"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">history_toggle_off</span>
		<h1 class="m-0 font-headline-md text-headline-md text-on-background">Time travel</h1>
	</div>
	<button
		onclick={load}
		class="flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary/40 hover:text-primary"
	>
		<span class="material-symbols-outlined text-sm">refresh</span> Refresh
	</button>
</header>

<div class="px-container-padding pb-12 pt-24">
	{#if error}<div
			class="mb-5 rounded-lg border border-error/30 bg-error-container/20 p-4 text-sm text-error"
		>
			{error}
		</div>{/if}

	<section class="mb-6 rounded-xl border border-outline-variant bg-surface-container p-5">
		<div class="flex flex-col justify-between gap-4 xl:flex-row xl:items-center">
			<div>
				<p class="mb-1 text-sm font-bold text-on-surface">Explore a captured point in time</p>
				<p class="m-0 text-sm text-on-surface-variant">
					Compare historical metrics with the tracked schema. Pick a window, then compare the latest
					captured state.
				</p>
			</div>
			<div class="flex flex-wrap items-end gap-3">
				<label class="text-xs text-on-surface-variant"
					>Database<select
						value={selectedDb?.id ?? ''}
						onchange={(event) => selectDatabase(eventValue(event))}
						class="mt-1 block rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface"
						><option value="" disabled>Select a database</option
						>{#each databases as database}<option value={database.id}>{database.name}</option
							>{/each}</select
					></label
				>
				<label class="text-xs text-on-surface-variant"
					>From<input
						type="datetime-local"
						bind:value={startDate}
						class="mt-1 block rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface"
					/></label
				>
				<label class="text-xs text-on-surface-variant"
					>To<input
						type="datetime-local"
						bind:value={endDate}
						class="mt-1 block rounded-lg border border-outline-variant bg-surface-container-high px-3 py-2 text-sm text-on-surface"
					/></label
				>
				<button
					onclick={load}
					class="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary">Travel</button
				>
			</div>
		</div>
		<div class="mt-4 flex flex-wrap gap-2">
			<button
				onclick={() => setRange(1)}
				class="rounded-md border border-outline-variant px-3 py-1 text-xs text-on-surface-variant hover:border-primary hover:text-primary"
				>24 hours</button
			><button
				onclick={() => setRange(7)}
				class="rounded-md border border-outline-variant px-3 py-1 text-xs text-on-surface-variant hover:border-primary hover:text-primary"
				>7 days</button
			><button
				onclick={() => setRange(30)}
				class="rounded-md border border-outline-variant px-3 py-1 text-xs text-on-surface-variant hover:border-primary hover:text-primary"
				>30 days</button
			>
		</div>
	</section>

	{#if loading}<div class="flex justify-center py-20">
			<span class="material-symbols-outlined animate-spin text-3xl text-primary"
				>progress_activity</span
			>
		</div>{:else}
		<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
			<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
				<p class="m-0 text-xs uppercase tracking-wider text-on-surface-variant">Server CPU</p>
				<p class="mt-2 text-2xl font-bold text-on-surface">
					{formatPercent(latestServer?.cpu_percent)}
				</p>
				<p class="mb-0 text-xs text-on-surface-variant">{formatDate(latestServer?.collected_at)}</p>
			</div>
			<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
				<p class="m-0 text-xs uppercase tracking-wider text-on-surface-variant">Server memory</p>
				<p class="mt-2 text-2xl font-bold text-on-surface">
					{formatPercent(latestServer?.ram_percent)}
				</p>
				<p class="mb-0 text-xs text-on-surface-variant">Latest captured sample</p>
			</div>
			<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
				<p class="m-0 text-xs uppercase tracking-wider text-on-surface-variant">Database size</p>
				<p class="mt-2 text-2xl font-bold text-on-surface">
					{formatBytes(latestDatabase?.size_bytes ?? null)}
				</p>
				<p class="mb-0 text-xs text-on-surface-variant">
					{formatDate(latestDatabase?.collected_at)}
				</p>
			</div>
			<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
				<p class="m-0 text-xs uppercase tracking-wider text-on-surface-variant">Tracked tables</p>
				<p class="mt-2 text-2xl font-bold text-on-surface">{formatNumber(schema?.tables.length)}</p>
				<p class="mb-0 text-xs text-on-surface-variant">Current schema remains available</p>
			</div>
		</div>

		<div class="mt-6 grid gap-6 xl:grid-cols-2">
			<section class="rounded-xl border border-outline-variant bg-surface-container">
				<div class="flex items-center justify-between border-b border-outline-variant px-5 py-4">
					<div>
						<h2 class="m-0 font-bold text-on-surface">Executed queries</h2>
						<p class="mb-0 mt-1 text-xs text-on-surface-variant">
							Most expensive query signatures in the selected window
						</p>
					</div>
					{#if selectedDb && hasData(queryData?.items)}<a
							href={`/analytics/${selectedDb.id}/query`}
							class="text-xs font-bold text-primary">Open Query</a
						>{/if}
				</div>
				{#if hasData(queryData?.items)}<div class="divide-y divide-outline-variant">
						{#each queryData?.items.slice(0, 5) ?? [] as query}<div class="px-5 py-3">
								<p class="m-0 truncate font-code-sm text-xs text-on-surface">
									{query.query_preview}
								</p>
								<p class="mb-0 mt-2 text-xs text-on-surface-variant">
									{formatNumber(query.execution_count)} executions · {formatNumber(
										query.total_duration_ms
									)} ms total · last seen {formatDate(query.last_seen)}
								</p>
							</div>{/each}
					</div>{:else}<div class="p-8 text-center text-sm text-on-surface-variant">
						No query snapshots for this window.
					</div>{/if}
			</section>

			<section class="rounded-xl border border-outline-variant bg-surface-container">
				<div class="border-b border-outline-variant px-5 py-4">
					<h2 class="m-0 font-bold text-on-surface">Server metrics</h2>
					<p class="mb-0 mt-1 text-xs text-on-surface-variant">
						CPU, memory, disk and I/O from captured host samples
					</p>
				</div>
				{#if hasData(serverData?.items)}<div class="grid grid-cols-2 gap-4 p-5 text-sm">
						<div>
							<p class="m-0 text-xs text-on-surface-variant">Disk usage</p>
							<p class="mt-1 font-bold text-on-surface">
								{formatPercent(latestServer?.disk_percent)}
							</p>
						</div>
						<div>
							<p class="m-0 text-xs text-on-surface-variant">I/O read</p>
							<p class="mt-1 font-bold text-on-surface">
								{formatBytes(latestServer?.read_bytes ?? null)}
							</p>
						</div>
						<div>
							<p class="m-0 text-xs text-on-surface-variant">I/O write</p>
							<p class="mt-1 font-bold text-on-surface">
								{formatBytes(latestServer?.write_bytes ?? null)}
							</p>
						</div>
						<div>
							<p class="m-0 text-xs text-on-surface-variant">Samples</p>
							<p class="mt-1 font-bold text-on-surface">{formatNumber(serverData?.items.length)}</p>
						</div>
					</div>{:else}<div class="p-8 text-center text-sm text-on-surface-variant">
						No server metric snapshots for this window.
					</div>{/if}
			</section>

			<section class="rounded-xl border border-outline-variant bg-surface-container">
				<div class="flex items-center justify-between border-b border-outline-variant px-5 py-4">
					<div>
						<h2 class="m-0 font-bold text-on-surface">Largest tables</h2>
						<p class="mb-0 mt-1 text-xs text-on-surface-variant">
							Latest table size within the selected window
						</p>
					</div>
					{#if selectedDb && hasData(tableData?.table_size_history)}<a
							href={`/analytics/${selectedDb.id}/data`}
							class="text-xs font-bold text-primary">Open Data</a
						>{/if}
				</div>
				{#if tableSummary.length}{#each tableSummary.slice(0, 5) as table}<div
							class="flex items-center justify-between border-b border-outline-variant px-5 py-3 last:border-0"
						>
							<span class="text-sm text-on-surface">{table.schema_name}.{table.table_name}</span
							><span class="text-sm font-bold text-on-surface">{formatBytes(table.size_bytes)}</span
							>
						</div>{/each}{:else}<div class="p-8 text-center text-sm text-on-surface-variant">
						No table metric snapshots for this window.
					</div>{/if}
			</section>

			<section class="rounded-xl border border-outline-variant bg-surface-container">
				<div class="flex items-center justify-between border-b border-outline-variant px-5 py-4">
					<div>
						<h2 class="m-0 font-bold text-on-surface">Indexes</h2>
						<p class="mb-0 mt-1 text-xs text-on-surface-variant">
							Usage and cache efficiency at the selected range
						</p>
					</div>
					{#if selectedDb && hasData(indexData?.items)}<a
							href={`/analytics/${selectedDb.id}/index`}
							class="text-xs font-bold text-primary">Open Index</a
						>{/if}
				</div>
				{#if hasData(indexData?.items)}{#each indexData?.items.slice(0, 5) ?? [] as index}<div
							class="flex items-center justify-between border-b border-outline-variant px-5 py-3 last:border-0"
						>
							<div>
								<p class="m-0 text-sm text-on-surface">{index.index_name}</p>
								<p class="mb-0 mt-1 text-xs text-on-surface-variant">
									{index.schema_name}.{index.table_name}
								</p>
							</div>
							<div class="text-right">
								<p class="m-0 text-sm font-bold text-on-surface">
									{formatPercent(index.hit_rate === null ? null : index.hit_rate * 100)}
								</p>
								<p class="mb-0 mt-1 text-xs text-on-surface-variant">
									{formatNumber(index.total_scans)} scans
								</p>
							</div>
						</div>{/each}{:else}<div class="p-8 text-center text-sm text-on-surface-variant">
						No index snapshots for this window.
					</div>{/if}
			</section>
		</div>

		<section class="mt-6 rounded-xl border border-outline-variant bg-surface-container">
			<div class="flex items-center justify-between border-b border-outline-variant px-5 py-4">
				<div>
					<h2 class="m-0 font-bold text-on-surface">Schema timeline</h2>
					<p class="mb-0 mt-1 text-xs text-on-surface-variant">
						Tracked structure and documentation changes — available even when analytics is inactive
					</p>
				</div>
				{#if selectedDb}<a href={`/schema/${selectedDb.id}`} class="text-xs font-bold text-primary"
						>Open Schema</a
					>{/if}
			</div>
			{#if latestSchemaEvents.length}<div class="divide-y divide-outline-variant">
					{#each latestSchemaEvents as item}<div class="flex gap-3 px-5 py-4">
							<span class="material-symbols-outlined text-primary"
								>{item.type === 'index'
									? 'data_object'
									: item.type === 'column'
										? 'view_column'
										: 'table_chart'}</span
							>
							<div>
								<p class="m-0 text-sm text-on-surface">
									{item.details ?? `${item.type} ${item.action}`}
								</p>
								<p class="mb-0 mt-1 text-xs text-on-surface-variant">
									{formatDate(item.changed_at)}
								</p>
							</div>
						</div>{/each}
				</div>{:else}<div class="p-8 text-center text-sm text-on-surface-variant">
					No tracked schema changes yet. The current schema is still available above.
				</div>{/if}
		</section>
	{/if}
</div>
