<script lang="ts">
	import { DEFAULT_ANALYTICS_PRESET } from '$lib/timeRange';
	import Spinner from '$lib/components/Spinner.svelte';
	import { onDestroy, onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';
	import {
		listDatabases,
		listServers,
		getQueryAnalytics,
		getQueryExecutionHistory,
		getQueryContext,
		formatBytes
	} from '$lib/api';
	import type {
		DatabaseListItem,
		ServerListItem,
		QueryAnalyticsResponse,
		QueryAnalyticsItem,
		QueryExecutionHistoryResponse,
		QueryExecutionHistoryItem,
		QueryContextResponse,
		AnalyticsPreset,
		QueryOrderBy,
		QueryOrderDir
	} from '$lib/api';

	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let selectedServer = $state('');

	let preset = $state<AnalyticsPreset>(DEFAULT_ANALYTICS_PRESET);
	let startDate = $state('');
	let endDate = $state('');
	let searchQuery = $state('');
	let excludeTerm = $state('commit, rollback, begin');
	let orderBy = $state<QueryOrderBy>('executions');
	let orderDir = $state<QueryOrderDir>('desc');
	let initialQueryHash = $state<string | null>(null);

	let loadingQueries = $state(true);
	let error = $state('');

	let queryResponse = $state<QueryAnalyticsResponse | null>(null);
	let selectedQuery = $state<QueryAnalyticsItem | null>(null);

	let loadingHistory = $state(false);
	let historyResponse = $state<QueryExecutionHistoryResponse | null>(null);
	let selectedExecution = $state<QueryExecutionHistoryItem | null>(null);

	let loadingContext = $state(false);
	let contextResponse = $state<QueryContextResponse | null>(null);
	let contextError = $state('');
	let queriesRequest: AbortController | undefined;
	let historyRequest: AbortController | undefined;
	let contextRequest: AbortController | undefined;
	let disposed = false;

	onDestroy(() => {
		disposed = true;
		queriesRequest?.abort();
		historyRequest?.abort();
		contextRequest?.abort();
	});

	let copiedSql = $state(false);
	let hoveredPoint = $state<{ x: number; y: number; item: QueryExecutionHistoryItem } | null>(null);

	const presets: { label: string; value: AnalyticsPreset }[] = [
		{ label: '1D', value: '1d' },
		{ label: '3D', value: '3d' },
		{ label: '1W', value: '1w' },
		{ label: '2W', value: '2w' },
		{ label: '1M', value: '1m' },
		{ label: 'Custom', value: 'custom' }
	];

	function parseExcludeTerms(value: string): string[] {
		return value
			.split(',')
			.map((term) => term.trim())
			.filter((term) => term.length > 0);
	}

	function parseSearchTerms(value: string): string[] {
		return value
			.split(',')
			.map((term) => term.trim())
			.filter((term) => term.length > 0);
	}

	function buildFiltersQueryString(): string {
		const params = new URLSearchParams();
		if (preset) params.set('preset', preset);
		if (preset === 'custom') {
			if (startDate) params.set('start', startDate);
			if (endDate) params.set('end', endDate);
		}
		for (const term of parseSearchTerms(searchQuery)) {
			params.append('search', term);
		}
		for (const term of parseExcludeTerms(excludeTerm)) {
			params.append('exclude', term);
		}
		if (selectedQuery?.query_hash) {
			params.set('query_hash', selectedQuery.query_hash);
		}
		params.set('order_by', orderBy);
		params.set('order_dir', orderDir);
		return params.toString();
	}

	function readFiltersFromUrl() {
		const params = $page.url.searchParams;
		const presetParam = params.get('preset');
		if (presetParam && presets.some((p) => p.value === presetParam)) {
			preset = presetParam as AnalyticsPreset;
		}
		if (params.has('start')) startDate = params.get('start') ?? '';
		if (params.has('end')) endDate = params.get('end') ?? '';
		if (params.has('search')) {
			searchQuery = params
				.getAll('search')
				.map((t) => t.trim())
				.filter((t) => t.length > 0)
				.join(', ');
		}
		if (params.has('exclude')) {
			excludeTerm = params
				.getAll('exclude')
				.map((t) => t.trim())
				.filter((t) => t.length > 0)
				.join(', ');
		}
		if (params.has('query_hash')) {
			initialQueryHash = params.get('query_hash');
		}
		const orderParam = params.get('order_by');
		if (
			orderParam === 'executions' ||
			orderParam === 'avg_duration' ||
			orderParam === 'max_duration' ||
			orderParam === 'total_duration'
		) {
			orderBy = orderParam as QueryOrderBy;
		}
		const dirParam = params.get('order_dir');
		if (dirParam === 'asc' || dirParam === 'desc') {
			orderDir = dirParam as QueryOrderDir;
		}
	}

	async function syncFiltersUrl() {
		if (!selectedDb) return;
		const queryString = buildFiltersQueryString();
		const target = `/analytics/${selectedDb.id}/deep${queryString ? `?${queryString}` : ''}`;
		await goto(target, { replaceState: true, keepFocus: true, noScroll: true });
	}

	async function loadDatabasesAndServers() {
		try {
			const [dbList, serverList] = await Promise.all([listDatabases(), listServers()]);
			databases = dbList;
			servers = serverList;

			const routeDbId = $page.params.database_id;
			const db = databases.find((d) => d.id === routeDbId) || databases[0];
			if (db) {
				selectedDb = db;
				selectedServer = db.server_id;
				selectedDatabaseId.set(db.id);
				selectedServerId.set(db.server_id);
			}
		} catch (err: any) {
			error = err.message || 'Failed to load database connections.';
		}
	}

	async function loadQueries() {
		const dbId = selectedDb?.id || $page.params.database_id;
		if (!dbId || disposed) return;

		queriesRequest?.abort();
		historyRequest?.abort();
		contextRequest?.abort();
		const request = (queriesRequest = new AbortController());
		loadingHistory = false;
		loadingContext = false;
		loadingQueries = true;
		error = '';
		try {
			const options: Parameters<typeof getQueryAnalytics>[1] = {
				orderBy,
				orderDir,
				limit: 50,
				signal: request.signal
			};
			if (preset === 'custom') {
				if (startDate)
					options.startDate = startDate ? new Date(startDate).toISOString() : undefined;
				if (endDate) options.endDate = endDate ? new Date(endDate).toISOString() : undefined;
			} else {
				options.preset = preset;
			}
			if (searchQuery.trim()) options.search = searchQuery.trim();
			const excludeTerms = parseExcludeTerms(excludeTerm);
			if (excludeTerms.length > 0) options.exclude = excludeTerms;

			const response = await getQueryAnalytics(dbId, options);
			if (request.signal.aborted) return;
			queryResponse = response;

			if (queryResponse && queryResponse.items.length > 0) {
				const target = initialQueryHash
					? queryResponse.items.find((i) => i.query_hash === initialQueryHash) ||
						queryResponse.items[0]
					: queryResponse.items[0];
				void selectQuery(target);
			} else {
				selectedQuery = null;
				historyResponse = null;
				selectedExecution = null;
				contextResponse = null;
			}
		} catch (err: any) {
			if (request.signal.aborted) return;
			error = err.message || 'Failed to load query analytics.';
		} finally {
			if (!request.signal.aborted) loadingQueries = false;
		}
	}

	async function selectQuery(item: QueryAnalyticsItem) {
		historyRequest?.abort();
		contextRequest?.abort();
		const request = (historyRequest = new AbortController());
		loadingContext = false;
		historyResponse = null;
		selectedQuery = item;
		selectedExecution = null;
		contextResponse = null;
		contextError = '';
		hoveredPoint = null;
		const dbId = selectedDb?.id || $page.params.database_id;
		if (!item.query_hash || !dbId) return;

		loadingHistory = true;
		void syncFiltersUrl();
		try {
			const response = await getQueryExecutionHistory(dbId, item.query_hash, {
				preset,
				startDate: preset === 'custom' && startDate ? new Date(startDate).toISOString() : undefined,
				endDate: preset === 'custom' && endDate ? new Date(endDate).toISOString() : undefined,
				limit: 2000,
				signal: request.signal
			});
			if (request.signal.aborted) return;
			historyResponse = response;
			if (historyResponse && historyResponse.items.length > 0) {
				// Auto-select latest execution point
				void selectExecution(historyResponse.items[historyResponse.items.length - 1]);
			}
		} catch (err: any) {
			if (request.signal.aborted) return;
			error = err.message || 'Failed to load query execution history.';
		} finally {
			if (!request.signal.aborted) loadingHistory = false;
		}
	}

	async function selectExecution(item: QueryExecutionHistoryItem) {
		contextRequest?.abort();
		const request = (contextRequest = new AbortController());
		selectedExecution = item;
		contextResponse = null;
		contextError = '';
		const dbId = selectedDb?.id || $page.params.database_id;
		if (!selectedQuery?.query_hash || !dbId) return;

		loadingContext = true;
		try {
			const response = await getQueryContext(
				dbId,
				selectedQuery.query_hash,
				item.collected_at,
				request.signal,
				{ source: item.source, userId: item.user_id, isToplevel: item.is_toplevel }
			);
			if (request.signal.aborted) return;
			contextResponse = response;
		} catch (err: any) {
			if (request.signal.aborted) return;
			contextError = err.message || 'Failed to load query context.';
		} finally {
			if (!request.signal.aborted) loadingContext = false;
		}
	}

	function toggleSort(field: QueryOrderBy) {
		if (orderBy === field) {
			orderDir = orderDir === 'desc' ? 'asc' : 'desc';
		} else {
			orderBy = field;
			orderDir = 'desc';
		}
		void syncFiltersUrl();
		void loadQueries();
	}

	function applyFilterChange() {
		void syncFiltersUrl();
		void loadQueries();
	}

	onMount(async () => {
		readFiltersFromUrl();
		await loadDatabasesAndServers();
		await loadQueries();
	});

	function formatDuration(ms: number | null): string {
		if (ms === null || ms === undefined) return '--';
		if (ms < 1000) return `${Math.round(ms)}ms`;
		return `${(ms / 1000).toFixed(2)}s`;
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '--';
		return d.toLocaleString();
	}

	function formatShortTime(iso: string): string {
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '';
		return d.toLocaleDateString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	async function copySql(sql: string) {
		try {
			await navigator.clipboard.writeText(sql);
			copiedSql = true;
			setTimeout(() => (copiedSql = false), 2000);
		} catch {}
	}

	// Responsive chart properties
	let chartWidth = $state(650);
	const chartHeight = 240;
	const padding = { top: 20, right: 30, bottom: 45, left: 60 };

	let maxDurationValue = $derived.by(() => {
		if (!historyResponse || historyResponse.items.length === 0) return 10;
		return Math.max(
			...historyResponse.items
				.filter((i) => i.source !== 'statements')
				.map((i) => i.duration_ms || 0),
			10
		);
	});
	let statementSnapshots = $derived(
		historyResponse?.items.filter((item) => item.source === 'statements') ?? []
	);

	let historyPoints = $derived.by(() => {
		if (!historyResponse || historyResponse.items.length === 0) return [];
		const items = historyResponse.items.filter((item) => item.source !== 'statements');
		if (items.length === 0) return [];
		const maxDuration = maxDurationValue;
		const minTime = new Date(items[0].collected_at).getTime();
		const maxTime = new Date(items[items.length - 1].collected_at).getTime();
		const timeRange = maxTime - minTime || 1;
		const usableWidth = chartWidth - padding.left - padding.right;
		const usableHeight = chartHeight - padding.top - padding.bottom;

		return items.map((item) => {
			const time = new Date(item.collected_at).getTime();
			const x =
				items.length === 1
					? padding.left + usableWidth / 2
					: padding.left + ((time - minTime) / timeRange) * usableWidth;
			const y = padding.top + usableHeight - ((item.duration_ms || 0) / maxDuration) * usableHeight;
			return { x, y, item };
		});
	});

	let historySvgPath = $derived.by(() => {
		if (historyPoints.length === 0) return '';
		return historyPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
	});

	let selectedPoint = $derived.by(() => {
		if (!selectedExecution || historyPoints.length === 0) return null;
		return historyPoints.find((p) => p.item.collected_at === selectedExecution?.collected_at);
	});
</script>

<svelte:head>
	<title>Deep Analytics - {selectedDb?.name ?? 'pgwarden'}</title>
</svelte:head>

<!-- Global Request Loading Progress Bar -->
{#if loadingQueries || loadingHistory || loadingContext}
	<div
		class="page-loading-bar fixed left-[var(--sidebar-width)] right-0 z-50 h-1 bg-surface-container overflow-hidden"
	>
		<div class="h-full bg-primary animate-pulse w-full"></div>
	</div>
{/if}

<!-- Fixed Header -->
<header
	class="fixed top-0 right-0 app-page-header z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">travel_explore</span>
		<h1 class="font-headline-md text-headline-md text-on-background m-0">Analytics</h1>
		<span class="font-label-caps text-[12px] text-on-surface-variant">/ Query / Deep</span>
		{#if selectedDb}
			<span class="font-label-caps text-[12px] text-on-surface-variant">{selectedDb.name}</span>
		{/if}
	</div>
	<button
		onclick={loadQueries}
		class="flex items-center gap-2 px-4 py-2 bg-surface-container border border-outline-variant text-on-surface rounded-lg font-bold text-base hover:border-primary/40 hover:text-primary transition-all duration-200 cursor-pointer"
	>
		{#if loadingQueries}<Spinner class="text-base text-primary" />{:else}<span
				class="material-symbols-outlined text-base"
				aria-hidden="true">refresh</span
			>{/if}
		Refresh
	</button>
</header>

<!-- Main Container -->
<div class="pt-24 px-container-padding pb-12">
	{#if error}
		<div
			class="mb-6 p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
		>
			<span class="material-symbols-outlined text-error">error</span>
			<p class="font-code-sm text-base text-error">{error}</p>
		</div>
	{/if}

	<!-- Controls & Filter Bar -->
	<div class="mb-6 flex flex-wrap items-center justify-between gap-4">
		<div class="flex flex-wrap items-center gap-3">
			<!-- Server Selector -->

			<!-- Database Selector -->
		</div>

		<!-- Time Presets -->
		<div
			class="flex flex-wrap items-center gap-1.5 bg-surface-container border border-outline-variant p-1 rounded-xl"
		>
			{#each presets as p}
				<button
					onclick={() => {
						preset = p.value;
						applyFilterChange();
					}}
					class="px-3 py-1 rounded-lg text-sm font-bold transition-all cursor-pointer {preset ===
					p.value
						? 'bg-primary text-on-primary shadow-sm'
						: 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high'}"
				>
					{p.label}
				</button>
			{/each}
		</div>
	</div>

	{#if loadingQueries && !queryResponse}
		<div class="flex flex-col items-center justify-center py-24">
			<Spinner class="text-4xl text-primary mb-3" />
			<span class="text-base font-medium text-on-surface-variant">Loading query analytics...</span>
		</div>
	{:else if !queryResponse}
		<div
			class="flex flex-col items-center justify-center py-20 bg-surface-container border border-outline-variant rounded-xl p-8"
		>
			<span class="material-symbols-outlined text-4xl text-on-surface-variant mb-2"
				>find_in_page</span
			>
			<h3 class="font-headline-md text-headline-md font-bold text-on-surface mb-1">
				No queries executed
			</h3>
			<p class="text-sm text-on-surface-variant max-w-sm text-center">
				No query execution metrics recorded for this database in the selected timeframe.
			</p>
		</div>
	{:else}
		<!-- Main Split View -->
		<div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
			<!-- Left Column: Top queries list & filters -->
			<div class="lg:col-span-5 flex flex-col space-y-3">
				<div
					class="bg-surface-container border border-outline-variant rounded-xl p-4 shadow-sm flex flex-col h-[560px]"
				>
					<!-- Header + Order By Buttons -->
					<div
						class="flex flex-wrap items-center justify-between gap-3 mb-3 pb-3 border-b border-outline-variant/60"
					>
						<div class="flex items-center gap-2">
							<span class="material-symbols-outlined text-primary text-lg">view_list</span>
							<h2 class="font-headline-md text-base font-bold text-on-surface">
								Top queries ({queryResponse.items.length})
							</h2>
						</div>

						<!-- Order By Controls -->
						<div
							class="flex items-center gap-1 bg-surface-container-high border border-outline-variant p-0.5 rounded-lg text-[13px]"
						>
							<button
								onclick={() => toggleSort('executions')}
								class="px-2 py-0.5 rounded font-medium transition-all cursor-pointer flex items-center gap-1 {orderBy ===
								'executions'
									? 'bg-primary text-on-primary font-bold shadow-sm'
									: 'text-on-surface-variant hover:text-on-surface'}"
								title="Order by executions count"
							>
								<span>Execs</span>
								{#if orderBy === 'executions'}
									<span class="material-symbols-outlined text-[13px]"
										>{orderDir === 'desc' ? 'arrow_downward' : 'arrow_upward'}</span
									>
								{/if}
							</button>
							<button
								onclick={() => toggleSort('avg_duration')}
								class="px-2 py-0.5 rounded font-medium transition-all cursor-pointer flex items-center gap-1 {orderBy ===
								'avg_duration'
									? 'bg-primary text-on-primary font-bold shadow-sm'
									: 'text-on-surface-variant hover:text-on-surface'}"
								title="Order by average execution duration"
							>
								<span>Avg time</span>
								{#if orderBy === 'avg_duration'}
									<span class="material-symbols-outlined text-[13px]"
										>{orderDir === 'desc' ? 'arrow_downward' : 'arrow_upward'}</span
									>
								{/if}
							</button>
						</div>
					</div>

					<!-- Search & Exclude Filters Box -->
					<div class="space-y-2 mb-3">
						<!-- Query Search -->
						<div class="relative flex items-center">
							<span
								class="material-symbols-outlined absolute left-2.5 text-base text-on-surface-variant pointer-events-none"
								>search</span
							>
							<input
								type="text"
								placeholder="Search query text..."
								bind:value={searchQuery}
								onchange={applyFilterChange}
								onkeydown={(e) => e.key === 'Enter' && applyFilterChange()}
								class="w-full bg-surface-container-high border border-outline-variant rounded-lg pl-9 pr-3 py-1 text-sm text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary"
							/>
						</div>

						<!-- Exclude Terms -->
						<div class="relative flex items-center">
							<span
								class="material-symbols-outlined absolute left-2.5 text-base text-on-surface-variant pointer-events-none"
								>block</span
							>
							<input
								type="text"
								placeholder="Exclude (e.g. commit, rollback, begin)"
								bind:value={excludeTerm}
								onchange={applyFilterChange}
								onkeydown={(e) => e.key === 'Enter' && applyFilterChange()}
								class="w-full bg-surface-container-high border border-outline-variant rounded-lg pl-9 pr-3 py-1 text-sm text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary"
								title="Comma-separated list of keywords to exclude"
							/>
						</div>
					</div>

					<!-- Query List -->
					<div class="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
						{#if queryResponse.items.length === 0}
							<div class="py-8 text-center text-sm text-on-surface-variant">
								No matching queries found.
							</div>
						{/if}

						{#each queryResponse.items as item}
							<!-- svelte-ignore a11y_click_events_have_key_events -->
							<!-- svelte-ignore a11y_no_static_element_interactions -->
							<div
								onclick={() => selectQuery(item)}
								class="p-3 rounded-lg border text-sm cursor-pointer transition-all {selectedQuery?.query_hash ===
								item.query_hash
									? 'bg-primary/10 border-primary/40 text-on-surface shadow-sm'
									: 'bg-surface-container-high/40 border-outline-variant/50 hover:border-outline-variant text-on-surface-variant hover:text-on-surface'}"
							>
								<div
									class="font-mono text-sm text-on-surface line-clamp-2 mb-2 leading-relaxed"
									title={item.query_preview}
								>
									{item.query_preview}
								</div>
								<div class="flex items-center justify-between text-[13px]">
									<span class="flex items-center gap-1 font-mono text-on-surface-variant">
										<span class="material-symbols-outlined text-[14px] text-primary"
											>play_arrow</span
										>
										{item.execution_count} execs
									</span>
									<span
										class="font-mono font-medium text-primary bg-primary/10 px-2 py-0.5 rounded"
									>
										{formatDuration(item.avg_duration_ms)} avg
									</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			</div>

			<!-- Right Column: History Timeline SVG Chart -->
			<div class="lg:col-span-7 flex flex-col space-y-3">
				<div
					class="bg-surface-container border border-outline-variant rounded-xl p-4 shadow-sm h-[560px] flex flex-col justify-between relative"
					bind:clientWidth={chartWidth}
				>
					<div class="flex items-center justify-between pb-3 border-b border-outline-variant/60">
						<div class="flex items-center gap-2">
							<span class="material-symbols-outlined text-primary text-lg">show_chart</span>
							<h2 class="font-headline-md text-base font-bold text-on-surface">
								Activity timeline
							</h2>
						</div>
						{#if loadingHistory}
							<div class="flex items-center gap-1.5 text-sm text-primary font-medium">
								<Spinner class="text-base" />
								<span>Loading points...</span>
							</div>
						{:else if historyResponse}
							<span class="font-mono text-sm text-on-surface-variant"
								>{historyPoints.length} activity points</span
							>
						{/if}
					</div>

					<div class="flex-1 flex items-center justify-center relative my-2">
						{#if historyResponse && historyPoints.length > 0}
							<svg viewBox="0 0 {chartWidth} {chartHeight}" class="w-full h-full overflow-visible">
								<!-- Y-Axis Grid Lines & Labels -->
								<line
									x1={padding.left}
									y1={padding.top}
									x2={chartWidth - padding.right}
									y2={padding.top}
									stroke="currentColor"
									stroke-opacity="0.1"
								/>
								<text
									x={padding.left - 8}
									y={padding.top + 4}
									text-anchor="end"
									class="font-mono text-[12px] fill-on-surface-variant"
								>
									{formatDuration(maxDurationValue)}
								</text>

								<line
									x1={padding.left}
									y1={(chartHeight - padding.bottom + padding.top) / 2}
									x2={chartWidth - padding.right}
									y2={(chartHeight - padding.bottom + padding.top) / 2}
									stroke="currentColor"
									stroke-opacity="0.1"
								/>
								<text
									x={padding.left - 8}
									y={(chartHeight - padding.bottom + padding.top) / 2 + 3}
									text-anchor="end"
									class="font-mono text-[12px] fill-on-surface-variant"
								>
									{formatDuration(maxDurationValue / 2)}
								</text>

								<line
									x1={padding.left}
									y1={chartHeight - padding.bottom}
									x2={chartWidth - padding.right}
									y2={chartHeight - padding.bottom}
									stroke="currentColor"
									stroke-opacity="0.2"
								/>
								<text
									x={padding.left - 8}
									y={chartHeight - padding.bottom + 3}
									text-anchor="end"
									class="font-mono text-[12px] fill-on-surface-variant"
								>
									0ms
								</text>

								<!-- X-Axis Timestamps Labels -->
								{#if historyPoints.length >= 1}
									<text
										x={padding.left}
										y={chartHeight - 12}
										text-anchor="start"
										class="font-mono text-[12px] fill-on-surface-variant font-medium"
									>
										{formatShortTime(historyPoints[0].item.collected_at)}
									</text>
									{#if historyPoints.length > 2}
										<text
											x={padding.left + (chartWidth - padding.left - padding.right) / 2}
											y={chartHeight - 12}
											text-anchor="middle"
											class="font-mono text-[12px] fill-on-surface-variant font-medium"
										>
											{formatShortTime(
												historyPoints[Math.floor(historyPoints.length / 2)].item.collected_at
											)}
										</text>
									{/if}
									{#if historyPoints.length > 1}
										<text
											x={chartWidth - padding.right}
											y={chartHeight - 12}
											text-anchor="end"
											class="font-mono text-[12px] fill-on-surface-variant font-medium"
										>
											{formatShortTime(historyPoints[historyPoints.length - 1].item.collected_at)}
										</text>
									{/if}
								{/if}

								<!-- Vertical Guide Line for Selected Point -->
								{#if selectedPoint}
									<line
										x1={selectedPoint.x}
										y1={padding.top}
										x2={selectedPoint.x}
										y2={chartHeight - padding.bottom}
										stroke="var(--color-primary, #14b8a6)"
										stroke-dasharray="3 3"
										stroke-opacity="0.6"
									/>
								{/if}

								<!-- Line Chart Trend -->
								<path
									d={historySvgPath}
									fill="none"
									stroke="var(--color-primary, #14b8a6)"
									stroke-width="2"
									stroke-linejoin="round"
									stroke-linecap="round"
								/>

								<!-- Interactive Circle Points with Hover Actions -->
								{#each historyPoints as point}
									{@const isSelected = selectedExecution?.collected_at === point.item.collected_at}
									{@const isHovered = hoveredPoint?.item.collected_at === point.item.collected_at}
									<!-- svelte-ignore a11y_click_events_have_key_events -->
									<!-- svelte-ignore a11y_no_static_element_interactions -->
									<g
										onmouseenter={() => (hoveredPoint = point)}
										onmouseleave={() => (hoveredPoint = null)}
										onclick={() => selectExecution(point.item)}
										class="cursor-pointer"
									>
										<circle
											cx={point.x}
											cy={point.y}
											r={isSelected ? 6 : isHovered ? 5.5 : 3.5}
											class="transition-all {isSelected
												? 'text-primary fill-primary stroke-white'
												: isHovered
													? 'text-primary fill-primary stroke-primary/50'
													: 'text-primary fill-primary opacity-80'}"
											stroke="var(--color-surface-container, #1e293b)"
											stroke-width={isSelected ? 2.5 : isHovered ? 2 : 1.5}
										/>
									</g>
								{/each}
							</svg>

							<!-- Hover Tooltip Popover -->
							{#if hoveredPoint}
								<div
									class="absolute z-30 pointer-events-none bg-surface-container-high border border-outline-variant rounded-lg p-2.5 shadow-floating font-mono text-sm text-on-surface space-y-1 transform -translate-x-1/2 -translate-y-full -mt-2 transition-all"
									style="left: {hoveredPoint.x}px; top: {hoveredPoint.y}px;"
								>
									<div class="flex items-center gap-2 font-bold text-primary text-[13px]">
										<span class="material-symbols-outlined text-sm">timer</span>
										<span>{formatDuration(hoveredPoint.item.duration_ms)}</span>
									</div>
									<div class="text-[12px] text-on-surface-variant">
										{formatDate(hoveredPoint.item.collected_at)}
									</div>
									{#if hoveredPoint.item.user_name || hoveredPoint.item.application_name}
										<div class="text-[12px] text-on-surface-variant">
											{hoveredPoint.item.user_name ?? ''}
											{hoveredPoint.item.application_name
												? `@ ${hoveredPoint.item.application_name}`
												: ''}
										</div>
									{/if}
									<div class="text-[12px] text-primary underline mt-1">Click to load context</div>
								</div>
							{/if}
						{:else if !loadingHistory}
							<div class="text-sm text-on-surface-variant font-medium">
								No activity samples for this query. Statement snapshots appear below when available.
							</div>
						{/if}
					</div>

					<div
						class="pt-2 border-t border-outline-variant/40 flex items-center justify-between text-[13px] font-mono text-on-surface-variant"
					>
						<span
							>Click any point on the chart to filter the context snapshot to that timestamp</span
						>
						{#if selectedExecution}
							<span class="text-primary font-bold"
								>{formatDate(selectedExecution.collected_at)}</span
							>
						{/if}
					</div>
				</div>
				{#if statementSnapshots.length > 0}
					<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
						<h3 class="font-bold mb-2">Statement snapshots</h3>
						<p class="text-xs text-on-surface-variant mb-3">
							Calls and average time describe valid intervals between snapshots. Select a row to
							inspect SQL, schema and collected statistics.
						</p>
						<div class="max-h-64 overflow-auto">
							{#each statementSnapshots as snapshot}
								<button
									onclick={() => selectExecution(snapshot)}
									class="block w-full text-left border-b border-outline-variant/30 px-2 py-2 text-xs hover:bg-surface-container-high cursor-pointer"
								>
									{formatDate(snapshot.collected_at)} · {snapshot.user_name ?? 'unknown'} ·
									{snapshot.is_toplevel ? 'top level' : 'nested'} ·
									{snapshot.calls_delta ?? '--'} calls · {formatDuration(snapshot.duration_ms)} average
								</button>
							{/each}
						</div>
					</div>
				{/if}
			</div>
		</div>

		<!-- Context Panel Details -->
		{#if selectedExecution}
			<div class="mt-8 space-y-6 relative">
				{#if loadingContext}
					<div
						class="absolute inset-0 bg-surface-bg/60 backdrop-blur-sm z-30 flex flex-col items-center justify-center rounded-xl py-12"
					>
						<Spinner class="text-3xl text-primary mb-2" />
						<span class="text-sm font-semibold text-on-surface"
							>Fetching environment snapshot...</span
						>
					</div>
				{/if}

				<!-- Header info -->
				<div class="bg-surface-container border border-outline-variant rounded-xl p-5 shadow-sm">
					<div
						class="flex flex-wrap items-center justify-between gap-4 mb-4 pb-4 border-b border-outline-variant/60"
					>
						<div class="flex items-center gap-3">
							<div
								class="w-10 h-10 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center"
							>
								<span class="material-symbols-outlined text-primary">travel_explore</span>
							</div>
							<div>
								<h3 class="font-headline-md text-base font-bold text-on-surface">
									{selectedExecution.source === 'statements'
										? 'Statement snapshot context'
										: 'Execution snapshot context'}
								</h3>
								<div
									class="flex items-center gap-3 text-sm text-on-surface-variant font-mono mt-0.5"
								>
									<span class="text-primary font-semibold"
										>{formatDate(selectedExecution.collected_at)}</span
									>
									{#if selectedExecution.user_name}
										<span
											>• User: <strong class="text-on-surface">{selectedExecution.user_name}</strong
											></span
										>
									{/if}
									{#if selectedExecution.application_name}
										<span
											>• App: <strong class="text-on-surface"
												>{selectedExecution.application_name}</strong
											></span
										>
									{/if}
								</div>
							</div>
						</div>
						<div class="flex items-center gap-3">
							<div class="text-right">
								<div class="font-label-caps text-[12px] text-on-surface-variant uppercase">
									{selectedExecution.source === 'statements'
										? 'Interval average duration'
										: 'Execution duration'}
								</div>
								<div class="font-mono text-lg font-bold text-primary">
									{formatDuration(selectedExecution.duration_ms)}
								</div>
							</div>
						</div>
					</div>

					<!-- SQL Code Box -->
					{#if contextResponse?.execution.query || selectedQuery?.query_preview}
						<div
							class="relative bg-surface-container-high border border-outline-variant rounded-lg p-3"
						>
							<div
								class="flex items-center justify-between mb-1.5 text-[12px] font-label-caps text-on-surface-variant uppercase"
							>
								<span>SQL Query Signature</span>
								<button
									onclick={() =>
										copySql(contextResponse?.execution.query || selectedQuery?.query_preview || '')}
									class="flex items-center gap-1 text-sm text-primary hover:underline cursor-pointer"
								>
									<span class="material-symbols-outlined text-base"
										>{copiedSql ? 'check' : 'content_copy'}</span
									>
									{copiedSql ? 'Copied' : 'Copy'}
								</button>
							</div>
							<pre
								class="font-mono text-sm text-on-surface whitespace-pre-wrap break-all max-h-36 overflow-y-auto custom-scrollbar m-0 leading-relaxed">{contextResponse
									?.execution.query || selectedQuery?.query_preview}</pre>
						</div>
					{/if}
				</div>

				{#if contextError}
					<div
						class="p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
					>
						<span class="material-symbols-outlined text-error">error</span>
						<span class="text-sm text-error font-mono">{contextError}</span>
					</div>
				{:else if contextResponse}
					{#if contextResponse.execution.source === 'statements'}
						<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
							<p class="text-sm text-on-surface-variant mb-3">
								This is aggregated statement data. Session state, locks and resource usage cannot be
								attributed to a single execution.
							</p>
							<details>
								<summary class="cursor-pointer text-sm font-bold"
									>Collected statement statistics</summary
								>
								<pre class="mt-3 max-h-80 overflow-auto text-xs">{JSON.stringify(
										contextResponse.execution.statement_data,
										null,
										2
									)}</pre>
							</details>
						</div>
					{:else}
						<!-- System Resource & Connection KPIs -->
						<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
							<!-- Server Metrics -->
							<div
								class="bg-surface-container border border-outline-variant rounded-xl p-5 shadow-sm"
							>
								<h4
									class="font-label-caps text-sm text-on-surface-variant tracking-wider uppercase mb-4 flex items-center gap-2"
								>
									<span class="material-symbols-outlined text-primary text-base">dns</span>
									Server Resource Usage
								</h4>
								<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg flex flex-col justify-between"
									>
										<div
											class="font-label-caps text-[12px] text-on-surface-variant uppercase flex items-center justify-between"
										>
											<span>CPU</span>
											{#if contextResponse.server_metrics.cpu_stale}
												<span
													class="text-[11px] text-status-warning bg-status-warning/10 px-1 py-0.5 rounded border border-status-warning/20 font-mono tracking-tighter shrink-0"
													title="Metric was recorded outside the 90s execution window">stale</span
												>
											{/if}
										</div>
										<div class="font-mono text-xl font-bold text-on-surface mt-1">
											{contextResponse.server_metrics.cpu_percent !== null
												? `${contextResponse.server_metrics.cpu_percent.toFixed(1)}%`
												: '--'}
										</div>
									</div>
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg flex flex-col justify-between"
									>
										<div
											class="font-label-caps text-[12px] text-on-surface-variant uppercase flex items-center justify-between"
										>
											<span>RAM</span>
											{#if contextResponse.server_metrics.ram_stale}
												<span
													class="text-[11px] text-status-warning bg-status-warning/10 px-1 py-0.5 rounded border border-status-warning/20 font-mono tracking-tighter shrink-0"
													title="Metric was recorded outside the 90s execution window">stale</span
												>
											{/if}
										</div>
										<div class="font-mono text-xl font-bold text-on-surface mt-1">
											{contextResponse.server_metrics.ram_percent !== null
												? `${contextResponse.server_metrics.ram_percent.toFixed(1)}%`
												: '--'}
										</div>
									</div>
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg flex flex-col justify-between"
									>
										<div
											class="font-label-caps text-[12px] text-on-surface-variant uppercase flex items-center justify-between"
										>
											<span>Disk</span>
											{#if contextResponse.server_metrics.disk_stale}
												<span
													class="text-[11px] text-status-warning bg-status-warning/10 px-1 py-0.5 rounded border border-status-warning/20 font-mono tracking-tighter shrink-0"
													title="Metric was recorded outside the 90s execution window">stale</span
												>
											{/if}
										</div>
										<div class="font-mono text-xl font-bold text-on-surface mt-1">
											{contextResponse.server_metrics.disk_percent !== null
												? `${contextResponse.server_metrics.disk_percent.toFixed(1)}%`
												: '--'}
										</div>
									</div>
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg flex flex-col justify-between"
									>
										<div
											class="font-label-caps text-[12px] text-on-surface-variant uppercase flex items-center justify-between"
										>
											<span>Disk I/O</span>
											{#if contextResponse.server_metrics.io_stale}
												<span
													class="text-[11px] text-status-warning bg-status-warning/10 px-1 py-0.5 rounded border border-status-warning/20 font-mono tracking-tighter shrink-0"
													title="Metric was recorded outside the 90s execution window">stale</span
												>
											{/if}
										</div>
										<div class="font-mono text-sm font-semibold text-on-surface mt-1">
											R: {formatBytes(contextResponse.server_metrics.read_bytes)}
										</div>
										<div class="font-mono text-sm font-semibold text-on-surface">
											W: {formatBytes(contextResponse.server_metrics.write_bytes)}
										</div>
									</div>
								</div>
							</div>

							<!-- Database Connections -->
							<div
								class="bg-surface-container border border-outline-variant rounded-xl p-5 shadow-sm"
							>
								<h4
									class="font-label-caps text-sm text-on-surface-variant tracking-wider uppercase mb-4 flex items-center gap-2"
								>
									<span class="material-symbols-outlined text-primary text-base">hub</span>
									Database Connection State
								</h4>
								<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg"
									>
										<div class="font-label-caps text-[12px] text-on-surface-variant uppercase">
											Active
										</div>
										<div class="font-mono text-xl font-bold text-primary mt-1">
											{contextResponse.database_connections.active ?? '--'}
										</div>
									</div>
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg"
									>
										<div class="font-label-caps text-[12px] text-on-surface-variant uppercase">
											Waiting (Lock)
										</div>
										<div
											class="font-mono text-xl font-bold {contextResponse.database_connections
												.waiting != null && contextResponse.database_connections.waiting > 0
												? 'text-status-warning'
												: 'text-on-surface'} mt-1"
										>
											{contextResponse.database_connections.waiting ?? '--'}
										</div>
									</div>
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg"
									>
										<div class="font-label-caps text-[12px] text-on-surface-variant uppercase">
											Idle
										</div>
										<div class="font-mono text-xl font-bold text-on-surface mt-1">
											{contextResponse.database_connections.idle ?? '--'}
										</div>
									</div>
									<div
										class="bg-surface-container-high border border-outline-variant/60 p-3 rounded-lg"
									>
										<div class="font-label-caps text-[12px] text-on-surface-variant uppercase">
											Idle in Tx
										</div>
										<div
											class="font-mono text-xl font-bold {contextResponse.database_connections
												.idle_in_transaction != null &&
											contextResponse.database_connections.idle_in_transaction > 0
												? 'text-status-warning'
												: 'text-on-surface'} mt-1"
										>
											{contextResponse.database_connections.idle_in_transaction ?? '--'}
										</div>
									</div>
								</div>
							</div>
						</div>
					{/if}
					<!-- Database Locks Section -->
					<div
						class="bg-surface-container border border-outline-variant rounded-xl p-5 shadow-sm space-y-4"
					>
						<h4
							class="font-label-caps text-sm text-on-surface-variant tracking-wider uppercase flex items-center gap-2"
						>
							<span class="material-symbols-outlined text-primary text-base">lock</span>
							Database Locks (Related Tables / PID) ({contextResponse.locks.length})
						</h4>
						{#if contextResponse.locks.length === 0}
							<div
								class="text-sm text-on-surface-variant bg-surface-container-high p-4 rounded-lg border border-outline-variant/60 text-center"
							>
								{contextResponse.execution.source === 'statements'
									? 'Locks are unavailable for aggregated statement snapshots.'
									: 'No lock conflicts recorded on related tables or query PID during this snapshot window.'}
							</div>
						{:else}
							<div
								class="overflow-x-auto rounded-lg border border-outline-variant/60 bg-surface-container-high"
							>
								<table class="w-full text-left font-mono text-sm border-collapse">
									<thead>
										<tr
											class="border-b border-outline-variant/60 font-label-caps text-[12px] text-on-surface-variant uppercase"
										>
											<th class="px-3 py-2">Table</th>
											<th class="px-3 py-2">Holder PID</th>
											<th class="px-3 py-2">Lock type</th>
											<th class="px-3 py-2">Mode</th>
											<th class="px-3 py-2">Granted</th>
											<th class="px-3 py-2">Query preview</th>
										</tr>
									</thead>
									<tbody class="divide-y divide-outline-variant/30">
										{#each contextResponse.locks as lock}
											<tr class="hover:bg-surface-container/60">
												<td class="px-3 py-2 text-on-surface font-medium"
													>{lock.table_name ?? '--'}</td
												>
												<td class="px-3 py-2 text-primary font-bold">{lock.holder_pid}</td>
												<td class="px-3 py-2 text-on-surface-variant">{lock.type}</td>
												<td class="px-3 py-2 text-on-surface-variant">{lock.mode}</td>
												<td
													class="px-3 py-2 font-semibold {lock.is_granted
														? 'text-status-healthy'
														: 'text-status-warning'}"
												>
													{lock.is_granted ? 'Granted' : 'Waiting'}
												</td>
												<td class="px-3 py-2 text-on-surface line-clamp-1 max-w-xs"
													>{lock.query_preview ?? '--'}</td
												>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
					</div>

					<!-- Tables & Index Context Section -->
					<div class="space-y-4 pt-2">
						<h3
							class="font-headline-md text-base font-bold text-on-surface flex items-center gap-2"
						>
							<span class="material-symbols-outlined text-primary text-base">table_chart</span>
							Accessed tables & index health ({contextResponse.tables.length})
						</h3>

						{#if contextResponse.tables.length === 0}
							<div
								class="bg-surface-container border border-outline-variant rounded-xl p-6 text-center space-y-2 shadow-sm"
							>
								<span class="material-symbols-outlined text-2xl text-on-surface-variant">info</span>
								<div class="text-sm font-semibold text-on-surface">
									No table hits mapped for this query signature
								</div>
								<p class="text-sm text-on-surface-variant max-w-md mx-auto leading-relaxed">
									No table relationships recorded for this query hash during execution context. To
									enable query-to-table correlation, ensure the <strong class="text-primary"
										>pgwarden analytics background service</strong
									> is active and running, which continuously parses SQL queries into table and column
									hits.
								</p>
							</div>
						{/if}

						{#each contextResponse.tables as table}
							<div
								class="bg-surface-container border border-outline-variant rounded-xl p-5 shadow-sm space-y-4"
							>
								<div
									class="flex items-center justify-between pb-3 border-b border-outline-variant/60"
								>
									<div class="flex items-center gap-2 font-mono text-base font-bold text-primary">
										<span>{table.schema_name}.{table.table_name}</span>
									</div>
									<span
										class="font-mono text-sm font-semibold text-on-surface-variant bg-surface-container-high px-2.5 py-1 rounded border border-outline-variant/50"
									>
										Size: {formatBytes(table.size_bytes)}
									</span>
								</div>

								<!-- Table Stats KPIs -->
								<div class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm font-mono">
									<div>
										<span
											class="font-label-caps text-[12px] text-on-surface-variant block uppercase"
											>Live tuples</span
										>
										<span class="text-on-surface font-semibold"
											>{table.n_live_tup?.toLocaleString() ?? '--'}</span
										>
									</div>
									<div>
										<span
											class="font-label-caps text-[12px] text-on-surface-variant block uppercase"
											>Dead tuples</span
										>
										<span
											class="font-semibold {table.n_dead_tup &&
											table.n_live_tup &&
											table.n_dead_tup / (table.n_live_tup + table.n_dead_tup) > 0.1
												? 'text-status-warning'
												: 'text-on-surface'}"
										>
											{table.n_dead_tup?.toLocaleString() ?? '--'}
										</span>
									</div>
									<div>
										<span
											class="font-label-caps text-[12px] text-on-surface-variant block uppercase"
											>Index scans</span
										>
										<span class="text-on-surface font-semibold"
											>{table.idx_scan?.toLocaleString() ?? '--'}</span
										>
									</div>
									<div>
										<span
											class="font-label-caps text-[12px] text-on-surface-variant block uppercase"
											>Seq scans</span
										>
										<span
											class="font-semibold {table.seq_scan && table.seq_scan > (table.idx_scan || 0)
												? 'text-status-warning'
												: 'text-on-surface'}"
										>
											{table.seq_scan?.toLocaleString() ?? '--'}
										</span>
									</div>
								</div>

								<!-- Table Indexes -->
								{#if table.indexes.length > 0}
									<div class="pt-2">
										<div
											class="font-label-caps text-[12px] text-on-surface-variant uppercase mb-2 tracking-wider"
										>
											Indexes
										</div>
										<div
											class="overflow-x-auto rounded-lg border border-outline-variant/60 bg-surface-container-high"
										>
											<table class="w-full text-left font-mono text-sm border-collapse">
												<thead>
													<tr
														class="border-b border-outline-variant/60 font-label-caps text-[12px] text-on-surface-variant uppercase"
													>
														<th class="px-3 py-2">Index name</th>
														<th class="px-3 py-2">Type</th>
														<th class="px-3 py-2 text-right">Scans</th>
														<th class="px-3 py-2 text-right">Hit rate</th>
													</tr>
												</thead>
												<tbody class="divide-y divide-outline-variant/30">
													{#each table.indexes as idx}
														<tr class="hover:bg-surface-container/60">
															<td class="px-3 py-2 text-on-surface font-medium">{idx.index_name}</td
															>
															<td class="px-3 py-2 text-on-surface-variant">{idx.index_type}</td>
															<td class="px-3 py-2 text-right text-on-surface"
																>{idx.scan_qt?.toLocaleString() ?? '--'}</td
															>
															<td
																class="px-3 py-2 text-right {idx.hit_rate !== null &&
																idx.hit_rate < 0.9
																	? 'text-status-warning'
																	: 'text-on-surface'} font-semibold"
															>
																{idx.hit_rate !== null
																	? `${(idx.hit_rate * 100).toFixed(1)}%`
																	: '--'}
															</td>
														</tr>
													{/each}
												</tbody>
											</table>
										</div>
									</div>
								{/if}
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>
