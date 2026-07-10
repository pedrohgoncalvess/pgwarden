<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';
	import { listDatabases, listServers, getQueryAnalytics } from '$lib/api';
	import type {
		DatabaseListItem,
		QueryAnalyticsResponse,
		QueryAnalyticsItem,
		AnalyticsPreset,
		ServerListItem
	} from '$lib/api';

	
	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let selectedServer = $state('');
	let data = $state<QueryAnalyticsResponse | null>(null);
	let loading = $state(true);
	let error = $state('');

	let preset = $state<AnalyticsPreset>('1w');
	let startDate = $state('');
	let endDate = $state('');
	let selectedUser = $state('');
	let selectedApplication = $state('');
	let selectedState = $state('');
	let searchTerm = $state('');
	let excludeTerm = $state('commit, begin');

	let expandedQuery = $state<string | null>(null);
	let pageOffset = $state(0);
	let timelineHoverIndex = $state<number | null>(null);
	let topQueryHoverIndex = $state<number | null>(null);
	let copiedQueryIndex = $state<number | null>(null);
	const pageLimit = 10;

	const presets: { label: string; value: AnalyticsPreset }[] = [
		{ label: '1D', value: '1d' },
		{ label: '3D', value: '3d' },
		{ label: '1W', value: '1w' },
		{ label: '2W', value: '2w' },
		{ label: '1M', value: '1m' },
		{ label: 'Custom', value: 'custom' }
	];

	const colors = [
		'#6366f1',
		'#22c55e',
		'#f59e0b',
		'#ef4444',
		'#8b5cf6',
		'#06b6d4',
		'#ec4899',
		'#84cc16'
	];

	
	function toInputDate(iso: string): string {
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '';
		return d.toISOString().slice(0, 16);
	}

	function fromInputDate(value: string): string {
		if (!value) return '';
		return new Date(value).toISOString();
	}

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

	function formatNumber(n: number | null): string {
		if (n === null || n === undefined) return '--';
		return n.toLocaleString();
	}

	function formatFilterLabel(value: string | null | undefined): string {
		if (value === null || value === undefined) return 'unknown';
		if (value.trim() === '') return 'blank';
		return value;
	}

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

	function readSearchTermsFromUrl(): string[] {
		return $page.url.searchParams
			.getAll('search')
			.map((term) => term.trim())
			.filter((term) => term.length > 0);
	}

	function buildSearchQueryString(value: string): string {
		const params = new URLSearchParams();
		for (const term of parseSearchTerms(value)) {
			params.append('search', term);
		}
		return params.toString();
	}

	function eventValue(event: Event): string {
		return (event.currentTarget as HTMLSelectElement).value;
	}

	let serverDatabases = $derived(
		selectedServer ? databases.filter((database) => database.server_id === selectedServer) : databases
	);

	function analyticsHref(databaseId: string): string {
		const queryString = buildSearchQueryString(searchTerm);
		return `/analytics/${databaseId}/query${queryString ? `?${queryString}` : ''}`;
	}

	async function selectServer(serverId: string) {
		selectedServer = serverId;
		selectedServerId.set(serverId);
		const database = databases.find((item) => item.server_id === serverId);
		if (database && database.id !== selectedDb?.id) {
			await selectDatabase(database, true);
		}
	}

	async function copyToClipboard(text: string) {
		try {
			await navigator.clipboard.writeText(text);
		} catch {
			const ta = document.createElement('textarea');
			ta.value = text;
			document.body.appendChild(ta);
			ta.select();
			document.execCommand('copy');
			document.body.removeChild(ta);
		}
	}

	function computeKpis(response: QueryAnalyticsResponse | null) {
		if (!response || response.items.length === 0) {
			return {
				totalExecutions: 0,
				uniqueQueries: 0,
				avgDuration: null,
				totalDuration: null,
				maxDuration: null,
				slowestQuery: null as QueryAnalyticsItem | null
			};
		}
		let totalExecutions = 0;
		let totalDuration = 0;
		let countWithDuration = 0;
		let maxDuration = -Infinity;
		let slowestQuery: QueryAnalyticsItem | null = null;

		for (const item of response.items) {
			totalExecutions += item.execution_count;
			if (item.avg_duration_ms !== null) {
				totalDuration += item.avg_duration_ms * item.execution_count;
				countWithDuration += item.execution_count;
			}
			if (item.max_duration_ms !== null && item.max_duration_ms > maxDuration) {
				maxDuration = item.max_duration_ms;
				slowestQuery = item;
			}
		}

		return {
			totalExecutions,
			uniqueQueries: response.items.length,
			avgDuration: countWithDuration > 0 ? totalDuration / countWithDuration : null,
			totalDuration: totalDuration > 0 ? totalDuration : null,
			maxDuration: isFinite(maxDuration) ? maxDuration : null,
			slowestQuery
		};
	}

	
	async function loadData(database: DatabaseListItem) {
		selectedDb = database;
		selectedDatabaseId.set(database.id);
		selectedServer = database.server_id;
		selectedServerId.set(database.server_id);
		loading = true;
		error = '';
		pageOffset = 0;
		try {
			const options: Parameters<typeof getQueryAnalytics>[1] = {};
			if (preset === 'custom') {
				options.startDate = startDate ? fromInputDate(startDate) : undefined;
				options.endDate = endDate ? fromInputDate(endDate) : undefined;
			} else {
				options.preset = preset;
			}
			if (selectedUser) options.userName = selectedUser;
			if (selectedApplication) options.applicationName = selectedApplication;
			if (selectedState) options.state = selectedState;
			if (searchTerm.trim()) options.search = searchTerm.trim();
			const excludeTerms = parseExcludeTerms(excludeTerm);
			if (excludeTerms.length > 0) options.exclude = excludeTerms;
			options.limit = pageLimit;

			data = await getQueryAnalytics(database.id, options);
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load query analytics.';
			data = null;
		} finally {
			loading = false;
		}
	}

	async function selectDatabase(database: DatabaseListItem, replace = false) {
		if (replace) {
			await goto(analyticsHref(database.id), { replaceState: true });
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
			searchTerm = readSearchTermsFromUrl().join(', ');
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			if (databases.length === 0) {
				return;
			}

			const routeDbId = $page.params.database_id;
			const db = databases.find((d) => d.id === routeDbId) ?? databases[0];
			if (db.id !== routeDbId) {
				await goto(analyticsHref(db.id), { replaceState: true });
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

	
	let kpis = $derived(computeKpis(data));

	let paginatedItems = $derived.by(() => {
		if (!data) return [];
		return data.items.slice(pageOffset, pageOffset + pageLimit);
	});

	let totalPages = $derived.by(() => {
		if (!data) return 0;
		return Math.ceil(data.total / pageLimit);
	});

	function changePage(delta: number) {
		const next = pageOffset + delta * pageLimit;
		if (next < 0 || next >= (data?.total || 0)) return;
		pageOffset = next;
	}

	
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

	function formatChartDate(iso: string): string {
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '';
		return d.toLocaleDateString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatChartDateFull(iso: string): string {
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '';
		return d.toLocaleString(undefined, {
			weekday: 'short',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
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

	
	let timelineExecutions = $derived.by(() => {
		const currentData = data;
		if (!currentData || currentData.timeline.length === 0) return [];
		const maxExec = Math.max(...currentData.timeline.map((p) => p.execution_count), 1);
		return currentData.timeline.map((p, i) => ({
			x: xScale(i, currentData.timeline.length),
			y: yScale(p.execution_count, maxExec),
			value: p.execution_count,
			timestamp: p.timestamp
		}));
	});

	let timelinePath = $derived.by(() => {
		if (timelineExecutions.length === 0) return '';
		return timelineExecutions.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
	});

	let timelineTooltip = $derived.by(() => {
		if (timelineHoverIndex === null || !data || data.timeline.length === 0) return null;
		const point = data.timeline[timelineHoverIndex];
		const exec = timelineExecutions[timelineHoverIndex];
		if (!exec) return null;
		return {
			timestamp: point.timestamp,
			fullDate: formatChartDateFull(point.timestamp),
			execution_count: point.execution_count,
			avg_duration_ms: point.avg_duration_ms,
			x: exec.x,
			y: exec.y
		};
	});

	
	let topQueries = $derived.by(() => {
		if (!data) return [];
		return data.items.slice(0, 5);
	});

	let maxPreviewChars = $derived.by(() => {
		if (barChartWidth < 360) return 8;
		if (barChartWidth < 480) return 12;
		if (barChartWidth < 640) return 16;
		return 20;
	});

	let barChartWidth = $state(0);
	const barChartHeight = 220;
	const barPadding = { top: 16, right: 16, bottom: 56, left: 56 };

	let topQueryBars = $derived.by(() => {
		if (topQueries.length === 0) return [];
		const maxCount = Math.max(...topQueries.map((q) => q.execution_count), 1);
		const usableWidth = barChartWidth - barPadding.left - barPadding.right;
		const barWidth = (usableWidth / topQueries.length) * 0.6;
		const step = usableWidth / topQueries.length;

		return topQueries.map((q, i) => ({
			x: barPadding.left + step * i + step * 0.2,
			y:
				barPadding.top +
				(barChartHeight - barPadding.top - barPadding.bottom) * (1 - q.execution_count / maxCount),
			width: barWidth,
			height:
				(barChartHeight - barPadding.top - barPadding.bottom) * (q.execution_count / maxCount),
			value: q.execution_count,
			label: q.query_preview,
			query: q.query_signature,
			index: i,
			color: colors[i % colors.length]
		}));
	});

	
	let userDistribution = $derived.by(() => {
		if (!data) return [];
		const dist = new Map<string, number>();
		for (const item of data.items) {
			for (const ub of item.user_breakdown) {
				const key = ub.user_name || 'unknown';
				dist.set(key, (dist.get(key) || 0) + ub.execution_count);
			}
		}
		return Array.from(dist.entries())
			.sort((a, b) => b[1] - a[1])
			.slice(0, 5);
	});

	let userBarChartWidth = $state(0);
	const userBarChartHeight = 220;

	let userBars = $derived.by(() => {
		if (userDistribution.length === 0) return [];
		const maxCount = Math.max(...userDistribution.map((u) => u[1]), 1);
		const usableWidth = userBarChartWidth - barPadding.left - barPadding.right;
		const barWidth = (usableWidth / userDistribution.length) * 0.6;
		const step = usableWidth / userDistribution.length;

		return userDistribution.map(([user, count], i) => ({
			x: barPadding.left + step * i + step * 0.2,
			y:
				barPadding.top +
				(userBarChartHeight - barPadding.top - barPadding.bottom) * (1 - count / maxCount),
			width: barWidth,
			height: (userBarChartHeight - barPadding.top - barPadding.bottom) * (count / maxCount),
			value: count,
			label: user,
			color: colors[i % colors.length]
		}));
	});
</script>


<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">search</span>
		<h1 class="font-headline-md text-headline-md text-on-background m-0">Analytics</h1>
		<span class="font-label-caps text-[10px] text-on-surface-variant">/ Query</span>
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


<div class="pt-24 px-container-padding pb-12">
	{#if error}
		<div
			class="mb-6 p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
		>
			<span class="material-symbols-outlined text-error">error</span>
			<p class="font-code-sm text-sm text-error">{error}</p>
		</div>
	{/if}

	{#if loading && databases.length === 0}
		<div class="flex items-center justify-center py-12">
			<svg
				class="h-8 w-8 animate-spin text-primary"
				xmlns="http://www.w3.org/2000/svg"
				fill="none"
				viewBox="0 0 24 24"
			>
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"
				></circle>
				<path
					class="opacity-75"
					fill="currentColor"
					d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
				></path>
			</svg>
		</div>
	{:else if databases.length === 0}
		<div class="flex flex-col items-center justify-center py-24">
			<div
				class="w-20 h-20 rounded-2xl bg-surface-container-high border border-outline-variant flex items-center justify-center mb-6"
			>
				<span class="material-symbols-outlined text-[40px] text-on-surface-variant">database</span>
			</div>
			<h2 class="font-headline-md text-headline-md font-bold text-on-surface mb-2">
				No databases connected
			</h2>
			<p class="text-body-md text-on-surface-variant max-w-md text-center mb-8">
				Connect a database from the Servers page to view query analytics.
			</p>
		</div>
	{:else}
		
		<div class="mb-6 flex flex-wrap items-center gap-3">
			<label class="flex items-center gap-2">
				<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Server</span>
				<select
					value={selectedServer}
					onchange={(event) => selectServer(eventValue(event))}
					disabled={servers.length <= 1}
					class="cursor-pointer rounded-lg border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs font-bold text-primary outline-none transition-all hover:bg-primary/15 focus:border-primary disabled:cursor-default disabled:opacity-80"
				>
					{#each servers as server}
						<option value={server.id}>{server.name}</option>
					{/each}
				</select>
			</label>
			<label class="flex items-center gap-2">
				<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Database</span>
				<select
					value={selectedDb?.id ?? ''}
					onchange={(event) => {
						const database = databases.find((item) => item.id === eventValue(event));
						if (database) selectDatabase(database, true);
					}}
					disabled={serverDatabases.length <= 1}
					class="cursor-pointer rounded-lg border border-secondary/30 bg-secondary/10 px-3 py-1.5 text-xs font-bold text-secondary outline-none transition-all hover:bg-secondary/15 focus:border-secondary disabled:cursor-default disabled:opacity-80"
				>
					{#each serverDatabases as db}
						<option value={db.id}>{db.name}</option>
					{/each}
				</select>
			</label>
		</div>

		
		<section class="mb-6 rounded-lg border border-outline-variant bg-surface-container p-4">
			<div class="flex flex-wrap items-end gap-4">
				<div class="flex flex-col gap-2">
					<span
						class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
						>Range</span
					>
					<div class="flex rounded-lg border border-outline-variant overflow-hidden">
						{#each presets as p}
							<button
								onclick={() => {
									preset = p.value;
								}}
								class="px-3 py-1.5 text-xs font-bold transition-colors {preset === p.value
									? 'bg-primary text-on-primary'
									: 'bg-surface-container text-on-surface-variant hover:bg-surface-variant'}"
							>
								{p.label}
							</button>
						{/each}
					</div>
				</div>

				{#if preset === 'custom'}
					<div class="flex flex-col gap-2">
						<span
							class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
							>Start</span
						>
						<input
							type="datetime-local"
							bind:value={startDate}
							class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
						/>
					</div>
					<div class="flex flex-col gap-2">
						<span
							class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
							>End</span
						>
						<input
							type="datetime-local"
							bind:value={endDate}
							class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none"
						/>
					</div>
				{/if}

				{#if data?.filters.users.length}
					<div class="flex flex-col gap-2">
						<span
							class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
							>User</span
						>
						<select
							bind:value={selectedUser}
							class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none min-w-[8rem]"
						>
							<option value="">All users</option>
							{#each data.filters.users as u}
								<option value={u ?? ''}>{formatFilterLabel(u)}</option>
							{/each}
						</select>
					</div>
				{/if}

				{#if data?.filters.applications.length}
					<div class="flex flex-col gap-2">
						<span
							class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
							>Application</span
						>
						<select
							bind:value={selectedApplication}
							class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none min-w-[8rem]"
						>
							<option value="">All apps</option>
							{#each data.filters.applications as a}
								<option value={a ?? ''}>{formatFilterLabel(a)}</option>
							{/each}
						</select>
					</div>
				{/if}

				{#if data?.filters.states.length}
					<div class="flex flex-col gap-2">
						<span
							class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
							>State</span
						>
						<select
							bind:value={selectedState}
							class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none min-w-[8rem]"
						>
							<option value="">All states</option>
							{#each data.filters.states as s}
								<option value={s ?? ''}>{formatFilterLabel(s)}</option>
							{/each}
						</select>
					</div>
				{/if}

				<div class="flex flex-col gap-2">
					<span
						class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
						>Search</span
					>
					<input
						type="text"
						bind:value={searchTerm}
						placeholder="Search query..."
						class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none w-48"
					/>
				</div>

				<div class="flex flex-col gap-2">
					<span
						class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant"
						>Exclude</span
					>
					<input
						type="text"
						bind:value={excludeTerm}
						placeholder="term1, term2..."
						class="bg-surface-container-high border border-outline-variant rounded-lg px-3 py-1.5 text-xs text-on-surface focus:border-primary focus:outline-none w-48"
					/>
				</div>

				<button
					onclick={applyFilters}
					disabled={loading}
					class="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-primary text-on-primary text-xs font-bold hover:bg-primary/90 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 cursor-pointer"
				>
					<span class="material-symbols-outlined text-[14px]">search</span>
					Search
				</button>
			</div>
		</section>

		
		<section class="mb-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
			<div class="rounded-lg border border-outline-variant bg-surface-container p-4">
				<p
					class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest mb-1"
				>
					Total executions
				</p>
				<p class="font-headline-md text-headline-md font-bold text-on-surface">
					{formatNumber(kpis.totalExecutions)}
				</p>
			</div>
			<div class="rounded-lg border border-outline-variant bg-surface-container p-4">
				<p
					class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest mb-1"
				>
					Unique queries
				</p>
				<p class="font-headline-md text-headline-md font-bold text-on-surface">
					{formatNumber(kpis.uniqueQueries)}
				</p>
			</div>
			<div class="rounded-lg border border-outline-variant bg-surface-container p-4">
				<p
					class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest mb-1"
				>
					Avg duration
				</p>
				<p class="font-headline-md text-headline-md font-bold text-on-surface">
					{formatDuration(kpis.avgDuration)}
				</p>
			</div>
			<div class="rounded-lg border border-outline-variant bg-surface-container p-4">
				<div class="flex items-center justify-between mb-1">
					<p class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest">
						Slowest query
					</p>
					{#if kpis.slowestQuery}
						<button
							onclick={() => copyToClipboard(kpis.slowestQuery!.query_signature)}
							class="text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
							title="Copy query"
						>
							<span class="material-symbols-outlined text-[16px]">content_copy</span>
						</button>
					{/if}
				</div>
				<p
					class="font-code-sm text-code-sm text-on-surface truncate"
					title={kpis.slowestQuery?.query_preview ?? ''}
				>
					{kpis.slowestQuery?.query_preview ?? '--'}
				</p>
				<p class="text-xs text-on-surface-variant mt-1">{formatDuration(kpis.maxDuration)}</p>
			</div>
		</section>

		
		<div class="mb-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
			
			<section
				class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden"
			>
				<div
					class="flex items-center gap-2 border-b border-outline-variant bg-surface-container-low px-4 py-3"
				>
					<span class="material-symbols-outlined text-sm text-primary">show_chart</span>
					<h2 class="m-0 font-headline-md text-headline-md">Executions over time</h2>
				</div>
				<div class="relative p-4" bind:clientWidth={timelineChartWidth}>
					{#if loading}
						<div class="flex items-center justify-center py-24">
							<svg
								class="h-8 w-8 animate-spin text-primary"
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
							>
								<circle
									class="opacity-25"
									cx="12"
									cy="12"
									r="10"
									stroke="currentColor"
									stroke-width="4"
								></circle>
								<path
									class="opacity-75"
									fill="currentColor"
									d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
								></path>
							</svg>
						</div>
					{:else if data?.timeline.length === 0}
						<div class="flex flex-col items-center justify-center py-24 text-on-surface-variant">
							<span class="material-symbols-outlined text-[40px] mb-3">insert_chart</span>
							<p class="text-sm">No timeline data available.</p>
						</div>
					{:else}
						<svg
							width="100%"
							height={timelineChartHeight}
							class="overflow-visible"
							role="img"
							aria-label="Executions over time"
							onmousemove={handleTimelineMouseMove}
							onmouseleave={handleTimelineMouseLeave}
						>
							{#if data && data.timeline.length > 0}
								{@const maxExec = Math.max(...data.timeline.map((p) => p.execution_count), 1)}
								
								{#each [0, 0.25, 0.5, 0.75, 1] as tick}
									{@const value = Math.round(maxExec * (1 - tick))}
									{@const y = yScale(value, maxExec)}
									<line
										x1={padding.left}
										y1={y}
										x2={timelineChartWidth - padding.right}
										y2={y}
										stroke="currentColor"
										stroke-opacity="0.1"
									/>
									<text
										x={padding.left - 8}
										y={y + 4}
										text-anchor="end"
										class="text-[10px] fill-on-surface-variant">{value}</text
									>
								{/each}

								
								{#each [0, Math.floor((data.timeline.length - 1) / 2), data.timeline.length - 1] as idx}
									{@const x = xScale(idx, data.timeline.length)}
									<text
										{x}
										y={timelineChartHeight - 12}
										text-anchor="middle"
										class="text-[10px] fill-on-surface-variant"
										>{formatChartDate(data.timeline[idx].timestamp)}</text
									>
								{/each}

								
								<path d={timelinePath} fill="none" stroke={colors[0]} stroke-width="2" />
								{#each timelineExecutions as pt}
									<circle cx={pt.x} cy={pt.y} r="3" fill={colors[0]} />
								{/each}

								
								{#if timelineHoverIndex !== null && timelineTooltip}
									<line
										x1={timelineTooltip.x}
										y1={padding.top}
										x2={timelineTooltip.x}
										y2={timelineChartHeight - padding.bottom}
										stroke="currentColor"
										stroke-opacity="0.3"
										stroke-dasharray="4 4"
									/>
									<circle
										cx={timelineTooltip.x}
										cy={timelineTooltip.y}
										r="5"
										fill={colors[0]}
										stroke="white"
										stroke-width="2"
									/>
								{/if}
							{/if}
						</svg>

						{#if timelineTooltip}
							<div
								class="pointer-events-none absolute right-4 top-4 z-10 rounded-lg border border-outline-variant bg-surface-container-high p-3 text-xs shadow-lg"
							>
								<p class="font-bold text-on-surface mb-1">{timelineTooltip.fullDate}</p>
								<p class="text-on-surface-variant">
									Executions: <span class="font-bold text-on-surface"
										>{timelineTooltip.execution_count}</span
									>
								</p>
								{#if timelineTooltip.avg_duration_ms !== null}
									<p class="text-on-surface-variant">
										Avg duration: <span class="font-bold text-on-surface"
											>{formatDuration(timelineTooltip.avg_duration_ms)}</span
										>
									</p>
								{/if}
							</div>
						{/if}
					{/if}
				</div>
			</section>

			
			<section
				class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden"
			>
				<div
					class="flex items-center gap-2 border-b border-outline-variant bg-surface-container-low px-4 py-3"
				>
					<span class="material-symbols-outlined text-sm text-primary">bar_chart</span>
					<h2 class="m-0 font-headline-md text-headline-md">Top queries by executions</h2>
				</div>
				<div class="p-4" bind:clientWidth={barChartWidth}>
					{#if loading}
						<div class="flex items-center justify-center py-24">
							<svg
								class="h-8 w-8 animate-spin text-primary"
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
							>
								<circle
									class="opacity-25"
									cx="12"
									cy="12"
									r="10"
									stroke="currentColor"
									stroke-width="4"
								></circle>
								<path
									class="opacity-75"
									fill="currentColor"
									d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
								></path>
							</svg>
						</div>
					{:else if topQueries.length === 0}
						<div class="flex flex-col items-center justify-center py-24 text-on-surface-variant">
							<span class="material-symbols-outlined text-[40px] mb-3">insert_chart</span>
							<p class="text-sm">No query data available.</p>
						</div>
					{:else}
						<svg width="100%" height={barChartHeight} class="overflow-visible">
							{#each [0, 0.5, 1] as tick}
								{@const maxCount = Math.max(...topQueries.map((q) => q.execution_count), 1)}
								{@const value = Math.round(maxCount * (1 - tick))}
								{@const y =
									barPadding.top + (barChartHeight - barPadding.top - barPadding.bottom) * tick}
								<line
									x1={barPadding.left}
									y1={y}
									x2={barChartWidth - barPadding.right}
									y2={y}
									stroke="currentColor"
									stroke-opacity="0.1"
								/>
								<text
									x={barPadding.left - 8}
									y={y + 4}
									text-anchor="end"
									class="text-[10px] fill-on-surface-variant">{value}</text
								>
							{/each}
							{#each topQueryBars as bar}
								<g
									role="button"
									tabindex="0"
									class="cursor-pointer"
									onmouseenter={() => (topQueryHoverIndex = bar.index)}
									onmouseleave={() => (topQueryHoverIndex = null)}
									onclick={() => {
										copyToClipboard(bar.query);
										copiedQueryIndex = bar.index;
										setTimeout(() => (copiedQueryIndex = null), 1200);
									}}
									onkeydown={(e: KeyboardEvent) => {
										if (e.key === 'Enter' || e.key === ' ') {
											e.preventDefault();
											copyToClipboard(bar.query);
											copiedQueryIndex = bar.index;
											setTimeout(() => (copiedQueryIndex = null), 1200);
										}
									}}
								>
									<rect
										x={bar.x}
										y={bar.y}
										width={bar.width}
										height={bar.height}
										fill={bar.color}
										rx="2"
										class="transition-opacity hover:opacity-80"
									/>
									<text
										x={bar.x + bar.width / 2}
										y={bar.y - 6}
										text-anchor="middle"
										class="text-[10px] fill-on-surface font-bold">{bar.value}</text
									>
									<text
										x={bar.x + bar.width / 2}
										y={barChartHeight - 12}
										text-anchor="middle"
										class="text-[9px] fill-on-surface-variant"
										>{bar.label.slice(0, maxPreviewChars)}{bar.label.length > maxPreviewChars
											? '...'
											: ''}</text
									>
								</g>
							{/each}
							{#if topQueryHoverIndex !== null}
								{@const bar = topQueryBars[topQueryHoverIndex]}
								{@const tooltipX = Math.min(
									Math.max(bar.x + bar.width / 2, 80),
									barChartWidth - 80
								)}
								{@const tooltipY = bar.y - 8}
								<g transform="translate({tooltipX}, {tooltipY})">
									<rect
										x="-75"
										y="-46"
										width="150"
										height="44"
										rx="6"
										fill="currentColor"
										class="text-surface-container-high"
									/>
									<text y="-26" text-anchor="middle" class="text-[10px] fill-on-surface font-bold"
										>{bar.value.toLocaleString()} executions</text
									>
									<text y="-10" text-anchor="middle" class="text-[9px] fill-on-surface-variant"
										>{copiedQueryIndex === bar.index ? 'Copied!' : 'Click to copy query'}</text
									>
								</g>
							{/if}
						</svg>
					{/if}
				</div>
			</section>

			
			<section
				class="rounded-lg border border-outline-variant bg-surface-container overflow-hidden lg:col-span-2"
			>
				<div
					class="flex items-center gap-2 border-b border-outline-variant bg-surface-container-low px-4 py-3"
				>
					<span class="material-symbols-outlined text-sm text-primary">group</span>
					<h2 class="m-0 font-headline-md text-headline-md">Executions by user</h2>
				</div>
				<div class="p-4" bind:clientWidth={userBarChartWidth}>
					{#if loading}
						<div class="flex items-center justify-center py-24">
							<svg
								class="h-8 w-8 animate-spin text-primary"
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
							>
								<circle
									class="opacity-25"
									cx="12"
									cy="12"
									r="10"
									stroke="currentColor"
									stroke-width="4"
								></circle>
								<path
									class="opacity-75"
									fill="currentColor"
									d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
								></path>
							</svg>
						</div>
					{:else if userDistribution.length === 0}
						<div class="flex flex-col items-center justify-center py-24 text-on-surface-variant">
							<span class="material-symbols-outlined text-[40px] mb-3">insert_chart</span>
							<p class="text-sm">No user data available.</p>
						</div>
					{:else}
						<svg width="100%" height={userBarChartHeight} class="overflow-visible">
							{#each [0, 0.5, 1] as tick}
								{@const maxCount = Math.max(...userDistribution.map((u) => u[1]), 1)}
								{@const value = Math.round(maxCount * (1 - tick))}
								{@const y =
									barPadding.top + (userBarChartHeight - barPadding.top - barPadding.bottom) * tick}
								<line
									x1={barPadding.left}
									y1={y}
									x2={userBarChartWidth - barPadding.right}
									y2={y}
									stroke="currentColor"
									stroke-opacity="0.1"
								/>
								<text
									x={barPadding.left - 8}
									y={y + 4}
									text-anchor="end"
									class="text-[10px] fill-on-surface-variant">{value}</text
								>
							{/each}
							{#each userBars as bar}
								<rect
									x={bar.x}
									y={bar.y}
									width={bar.width}
									height={bar.height}
									fill={bar.color}
									rx="2"
								/>
								<text
									x={bar.x + bar.width / 2}
									y={bar.y - 6}
									text-anchor="middle"
									class="text-[10px] fill-on-surface font-bold">{bar.value}</text
								>
								<text
									x={bar.x + bar.width / 2}
									y={userBarChartHeight - 12}
									text-anchor="middle"
									class="text-[9px] fill-on-surface-variant">{bar.label}</text
								>
							{/each}
						</svg>
					{/if}
				</div>
			</section>
		</div>

		
		<section class="overflow-hidden rounded-lg border border-outline-variant bg-surface-container">
			<div
				class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3"
			>
				<div class="flex items-center gap-2">
					<span class="material-symbols-outlined text-sm text-primary">list</span>
					<h2 class="m-0 font-headline-md text-headline-md">Queries</h2>
				</div>
				<span class="font-code-sm text-code-sm text-on-surface-variant">
					{data?.items.length ?? 0} queries
				</span>
			</div>

			<div class="overflow-x-auto">
				<table class="w-full text-left border-collapse">
					<thead class="bg-surface-container-high">
						<tr>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>QUERY</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>EXECUTIONS</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>AVG DURATION</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>MAX DURATION</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>TOTAL DURATION</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>USERS</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>APPS</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>LAST SEEN</th
							>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-variant/20">
						{#if loading}
							<tr>
								<td colspan="8" class="px-4 py-8 text-center text-on-surface-variant text-sm">
									<div class="flex items-center justify-center gap-2">
										<svg
											class="animate-spin h-4 w-4 text-primary"
											xmlns="http://www.w3.org/2000/svg"
											fill="none"
											viewBox="0 0 24 24"
										>
											<circle
												class="opacity-25"
												cx="12"
												cy="12"
												r="10"
												stroke="currentColor"
												stroke-width="4"
											></circle>
											<path
												class="opacity-75"
												fill="currentColor"
												d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
											></path>
										</svg>
										Loading queries…
									</div>
								</td>
							</tr>
						{:else if !data || data.items.length === 0}
							<tr>
								<td colspan="8" class="px-4 py-8 text-center text-on-surface-variant text-sm">
									No queries found for the selected filters.
								</td>
							</tr>
						{:else}
							{#each paginatedItems as item (item.query_signature)}
								<tr
									class="hover:bg-surface-variant/20 transition-colors cursor-pointer"
									onclick={() =>
										(expandedQuery =
											expandedQuery === item.query_signature ? null : item.query_signature)}
								>
									<td class="px-4 py-3">
										<div class="flex items-start gap-2">
											<div class="min-w-0">
												<p
													class="font-code-sm text-code-sm text-on-surface font-bold truncate max-w-xs"
													title={item.query_signature}
												>
													{item.query_preview}
												</p>
												<p class="text-[10px] text-on-surface-variant truncate max-w-xs">
													{item.query_signature}
												</p>
											</div>
											<button
												onclick={(e) => {
													e.stopPropagation();
													copyToClipboard(item.query_signature);
												}}
												class="text-on-surface-variant hover:text-primary transition-colors cursor-pointer shrink-0"
												title="Copy query"
											>
												<span class="material-symbols-outlined text-[16px]">content_copy</span>
											</button>
										</div>
									</td>
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface"
										>{formatNumber(item.execution_count)}</td
									>
									<td class="px-4 py-3 text-sm text-on-surface-variant"
										>{formatDuration(item.avg_duration_ms)}</td
									>
									<td class="px-4 py-3 text-sm text-on-surface-variant"
										>{formatDuration(item.max_duration_ms)}</td
									>
									<td class="px-4 py-3 text-sm text-on-surface-variant"
										>{formatDuration(item.total_duration_ms)}</td
									>
									<td class="px-4 py-3 text-sm text-on-surface-variant">{item.unique_users}</td>
									<td class="px-4 py-3 text-sm text-on-surface-variant"
										>{item.unique_applications}</td
									>
									<td class="px-4 py-3 text-sm text-on-surface-variant"
										>{formatDate(item.last_seen)}</td
									>
								</tr>
								{#if expandedQuery === item.query_signature}
									<tr class="bg-surface-container-high/50">
										<td colspan="8" class="px-4 py-3">
											<div class="mb-3">
												<div class="flex items-center justify-between mb-1">
													<p
														class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest"
													>
														Normalized signature
													</p>
													<button
														onclick={(e) => {
															e.stopPropagation();
															copyToClipboard(item.query_signature);
														}}
														class="text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
														title="Copy query"
													>
														<span class="material-symbols-outlined text-[16px]">content_copy</span>
													</button>
												</div>
												<pre
													class="font-code-sm text-code-sm text-on-surface bg-surface-container-high border border-outline-variant rounded p-2 overflow-x-auto">{item.query_signature}</pre>
											</div>
											<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
												<div>
													<p
														class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest mb-1"
													>
														Users
													</p>
													<ul class="text-xs text-on-surface space-y-1">
														{#each item.user_breakdown as ub}
															<li>
																<span class="font-bold">{ub.user_name ?? 'unknown'}</span>: {ub.execution_count}
															</li>
														{/each}
													</ul>
												</div>
												<div>
													<p
														class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest mb-1"
													>
														Applications
													</p>
													<ul class="text-xs text-on-surface space-y-1">
														{#each item.application_breakdown as ab}
															<li>
																<span class="font-bold">{ab.application_name ?? 'unknown'}</span>: {ab.execution_count}
															</li>
														{/each}
													</ul>
												</div>
											</div>
										</td>
									</tr>
								{/if}
							{/each}
						{/if}
					</tbody>
				</table>
			</div>

			
			{#if data && data.items.length > pageLimit}
				<div class="flex items-center justify-between border-t border-outline-variant px-4 py-3">
					<button
						onclick={() => changePage(-1)}
						disabled={pageOffset === 0 || loading}
						class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-on-surface text-xs font-bold hover:bg-surface-variant disabled:opacity-50 cursor-pointer"
					>
						<span class="material-symbols-outlined text-[14px]">chevron_left</span>
						Previous
					</button>
					<span class="text-xs text-on-surface-variant font-code-sm">
						Page {Math.floor(pageOffset / pageLimit) + 1} of {totalPages}
					</span>
					<button
						onclick={() => changePage(1)}
						disabled={pageOffset + pageLimit >= (data?.items.length || 0) || loading}
						class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-on-surface text-xs font-bold hover:bg-surface-variant disabled:opacity-50 cursor-pointer"
					>
						Next
						<span class="material-symbols-outlined text-[14px]">chevron_right</span>
					</button>
				</div>
			{/if}
		</section>
	{/if}
</div>
