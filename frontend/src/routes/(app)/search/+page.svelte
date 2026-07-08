<script lang="ts">
	import { onDestroy, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		listDatabases,
		listServers,
		listTagAssignments,
		searchMetadata,
		type DatabaseListItem,
		type MetadataSearchResult,
		type ServerListItem,
		type TagAssignment
	} from '$lib/api';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';

	let query = $state($page.url.searchParams.get('q') ?? '');
	let results = $state<MetadataSearchResult[]>([]);
	let loading = $state(false);
	let error = $state('');
	let searched = $state(false);
	let quickTimeout = $state<ReturnType<typeof setTimeout> | null>(null);
	let semanticTimeout = $state<ReturnType<typeof setTimeout> | null>(null);
	let searchRequestId = 0;

	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let assignments = $state<TagAssignment[]>([]);
	let assignmentsLoading = $state(false);
	let serverFilter = $state($page.url.searchParams.get('server_id') ?? '');
	let databaseFilter = $state($page.url.searchParams.get('database_id') ?? '');
	const filteredDatabases = $derived(
		serverFilter ? databases.filter((database) => database.server_id === serverFilter) : databases
	);
	const activeServer = $derived(servers.find((server) => server.id === serverFilter) ?? null);
	const activeDatabase = $derived(databases.find((database) => database.id === databaseFilter) ?? null);
	const hasFilters = $derived(Boolean(serverFilter || databaseFilter));
	const visibleResultCounts = $derived.by(() => {
		const counts = new Map<MetadataSearchResult['type'], number>();
		for (const result of results) {
			counts.set(result.type, (counts.get(result.type) ?? 0) + 1);
		}
		return Array.from(counts.entries()).map(([type, count]) => ({ type, count }));
	});

	onMount(async () => {
		try {
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			if (!serverFilter && $selectedServerId) serverFilter = $selectedServerId;
			if (!databaseFilter && $selectedDatabaseId) databaseFilter = $selectedDatabaseId;
			normalizeFilters();
			if (query.trim()) await runSearch(true);
		} catch (err: any) {
			handleError(err, 'Failed to initialize search.');
		}
	});

	onDestroy(() => clearSearchTimeouts());

	function handleError(err: any, fallback: string) {
		if (err.message?.includes('401')) {
			localStorage.removeItem('token');
			window.location.href = '/login';
			return;
		}
		error = err.message || fallback;
	}

	function normalizeFilters() {
		if (databaseFilter) {
			const database = databases.find((item) => item.id === databaseFilter);
			if (database) {
				serverFilter = database.server_id;
				return;
			}
			databaseFilter = '';
		}

		if (serverFilter && !servers.some((server) => server.id === serverFilter)) {
			serverFilter = '';
		}
	}

	function eventValue(event: Event): string {
		return (event.currentTarget as HTMLSelectElement).value;
	}

	function selectServerFilter(value: string) {
		serverFilter = value;
		if (!value) {
			databaseFilter = '';
			return;
		}
		if (databaseFilter && !databases.some((database) => database.id === databaseFilter && database.server_id === value)) {
			databaseFilter = '';
		}
	}

	function selectDatabaseFilter(value: string) {
		databaseFilter = value;
		const database = databases.find((item) => item.id === value);
		if (database) serverFilter = database.server_id;
	}

	function useCurrentContext() {
		if ($selectedDatabaseId) {
			const database = databases.find((item) => item.id === $selectedDatabaseId);
			if (database) {
				databaseFilter = database.id;
				serverFilter = database.server_id;
				return;
			}
		}
		serverFilter = $selectedServerId ?? '';
		databaseFilter = '';
	}

	function clearFilters() {
		serverFilter = '';
		databaseFilter = '';
	}

	async function runSearch(semantic: boolean) {
		const term = query.trim();
		if (!term) return;
		const requestId = ++searchRequestId;

		try {
			loading = true;
			error = '';
			searched = true;
			const response = await searchMetadata({
				q: term,
				server_id: serverFilter || undefined,
				database_id: databaseFilter || undefined,
				limit: 25,
				semantic
			});
			if (requestId !== searchRequestId) return;
			results = response.results;
			loadTagsForResults(response.results);

			const params = new URLSearchParams();
			params.set('q', term);
			if (serverFilter) params.set('server_id', serverFilter);
			if (databaseFilter) params.set('database_id', databaseFilter);
			await goto(`?${params.toString()}`, { replaceState: true, keepFocus: true });
		} catch (err: any) {
			if (requestId === searchRequestId) handleError(err, 'Failed to search metadata.');
		} finally {
			if (requestId === searchRequestId) loading = false;
		}
	}

	function onInputKeydown(event: KeyboardEvent) {
		if (event.key === 'Enter') {
			clearSearchTimeouts();
			runSearch(true);
		}
	}

	function clearQuickTimeout() {
		if (quickTimeout) {
			clearTimeout(quickTimeout);
			quickTimeout = null;
		}
	}

	function clearSemanticTimeout() {
		if (semanticTimeout) {
			clearTimeout(semanticTimeout);
			semanticTimeout = null;
		}
	}

	function clearSearchTimeouts() {
		clearQuickTimeout();
		clearSemanticTimeout();
	}

	function scheduleQuickSearch() {
		clearQuickTimeout();
		quickTimeout = setTimeout(() => {
			quickTimeout = null;
			if (query.trim()) runSearch(false);
		}, 250);
	}

	function scheduleSemanticSearch() {
		clearSemanticTimeout();
		semanticTimeout = setTimeout(() => {
			semanticTimeout = null;
			if (query.trim()) runSearch(true);
		}, 2000);
	}

	function onInputSearch() {
		clearSearchTimeouts();
		if (!query.trim()) {
			results = [];
			searched = false;
			error = '';
			return;
		}
		scheduleQuickSearch();
		scheduleSemanticSearch();
	}

	async function loadTagsForResults(newResults: MetadataSearchResult[]) {
		const databaseIds = [
			...new Set(newResults.map((result) => result.database_id).filter((id): id is string => Boolean(id)))
		];
		if (databaseIds.length === 0) {
			assignments = [];
			return;
		}

		try {
			assignmentsLoading = true;
			const perDatabase = await Promise.all(databaseIds.map((id) => listTagAssignments(id)));
			assignments = perDatabase.flat();
		} catch {
			assignments = [];
		} finally {
			assignmentsLoading = false;
		}
	}

	function resultTags(result: MetadataSearchResult): TagAssignment[] {
		return assignments.filter((assignment) => matchesResult(assignment, result));
	}

	function matchesResult(assignment: TagAssignment, result: MetadataSearchResult): boolean {
		if (assignment.scope !== 'doc' || result.type === 'tag') return false;
		if (result.type === 'database') {
			return assignment.target_type === 'database' && assignment.database_id === result.database_id;
		}
		if (result.type === 'schema') {
			return (
				assignment.target_type === 'schema' &&
				assignment.database_id === result.database_id &&
				assignment.target_label === result.schema_name
			);
		}
		return assignment.target_type === result.type && assignment.target_id === result.id;
	}

	function targetKey(result: MetadataSearchResult): string | null {
		if (!result.database_id) return null;
		switch (result.type) {
			case 'database':
				return `database:${result.database_id}`;
			case 'schema':
				return result.schema_name ? `schema:${result.schema_name}` : null;
			case 'table':
			case 'column':
			case 'index':
				return result.id ? `${result.type}:${result.id}` : null;
			default:
				return null;
		}
	}

	function docHref(result: MetadataSearchResult): string {
		if (!result.database_id) return '#';
		const target = targetKey(result);
		return target ? `/metadata/${result.database_id}/documentation?target=${encodeURIComponent(target)}` : '#';
	}

	function schemaViewHref(result: MetadataSearchResult): string {
		if (!result.database_id) return '#';
		const params = new URLSearchParams();
		const tableId = result.table_id ?? (result.type === 'table' ? result.id : null);
		if (tableId) params.set('table', tableId);
		if (result.schema_name) params.set('schema', result.schema_name);
		const queryString = params.toString();
		return `/schema/${result.database_id}${queryString ? `?${queryString}` : ''}`;
	}

	function hasSchemaView(result: MetadataSearchResult): boolean {
		return Boolean(
			result.database_id &&
				(result.schema_name ||
					result.table_id ||
					result.type === 'table' ||
					result.type === 'column' ||
					result.type === 'index')
		);
	}

	function indexAnalyticsHref(result: MetadataSearchResult): string {
		if (!result.database_id || result.type !== 'index' || !result.name) return '#';
		return `/analytics/${result.database_id}/index?search=${encodeURIComponent(result.name)}`;
	}

	function tableQueryAnalyticsHref(result: MetadataSearchResult): string {
		if (!result.database_id || result.type !== 'table' || !result.schema_name || !result.table_name) return '#';
		const params = new URLSearchParams();
		if (result.schema_name === 'public') {
			params.append('search', `from public.${result.table_name}`);
			params.append('search', `from ${result.table_name}`);
		} else {
			params.append('search', `from ${result.schema_name}.${result.table_name}`);
		}
		return `/analytics/${result.database_id}/query?${params.toString()}`;
	}

	function resultHref(result: MetadataSearchResult): string {
		return docHref(result);
	}

	function typeIcon(type: MetadataSearchResult['type']): string {
		return {
			database: 'database',
			schema: 'schema',
			table: 'table',
			column: 'view_column',
			index: 'planner_review',
			tag: 'label'
		}[type] ?? 'search';
	}

	function typeLabel(type: MetadataSearchResult['type']): string {
		return type.charAt(0).toUpperCase() + type.slice(1);
	}

	function typeTone(type: MetadataSearchResult['type']): string {
		return (
			{
				database: 'bg-primary/10 text-primary border-primary/20',
				schema: 'bg-tertiary/10 text-tertiary border-tertiary/20',
				table: 'bg-secondary-container text-on-secondary-container border-outline-variant',
				column: 'bg-surface-container-high text-on-surface border-outline-variant',
				index: 'bg-error/10 text-error border-error/20',
				tag: 'bg-primary-container text-on-primary-container border-outline-variant'
			}[type] ?? 'bg-surface-container-high text-on-surface border-outline-variant'
		);
	}

	function resultScore(result: MetadataSearchResult): number {
		return Math.round(Math.max(0, Math.min(1, result.score)) * 100);
	}
</script>

<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
>
	<span class="material-symbols-outlined text-primary">search</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Search</h1>
</header>

<div class="pt-24 px-container-padding pb-12">
	<section class="mb-6 rounded-lg border border-outline-variant bg-surface-container p-4 shadow-sm">
		<div class="flex flex-col gap-4">
			<div class="flex flex-col gap-3 lg:flex-row">
				<div
					class="flex min-h-14 flex-1 items-center gap-3 rounded-lg border border-outline-variant bg-surface-container-high px-4 transition-colors focus-within:border-primary focus-within:bg-surface"
				>
					<span class="material-symbols-outlined text-[22px] text-primary">search</span>
					<input
						type="text"
						bind:value={query}
						oninput={onInputSearch}
						onkeydown={onInputKeydown}
						placeholder="Search metadata..."
						class="min-w-0 flex-1 bg-transparent text-base text-on-surface outline-none placeholder:text-on-surface-variant/60"
					/>
					{#if loading}
						<span class="material-symbols-outlined animate-spin text-on-surface-variant">progress_activity</span>
					{/if}
				</div>

				<button
					type="button"
					onclick={() => runSearch(true)}
					disabled={loading || !query.trim()}
					class="flex min-h-14 items-center justify-center gap-2 rounded-lg bg-primary px-5 text-sm font-bold text-on-primary transition-all active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
				>
					<span class="material-symbols-outlined text-[18px]">search</span>
					Search
				</button>
			</div>

			<div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
				<label class="flex flex-col gap-1.5 text-xs font-bold uppercase tracking-wide text-on-surface-variant">
					Server
					<div class="relative">
						<span class="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-on-surface-variant">
							dns
						</span>
						<select
							value={serverFilter}
							onchange={(event) => selectServerFilter(eventValue(event))}
							class="h-11 w-full rounded-lg border border-outline-variant bg-surface-container-high py-2 pl-10 pr-8 text-sm font-medium text-on-surface outline-none focus:border-primary"
						>
							<option value="">All servers</option>
							{#each servers as server}
								<option value={server.id}>{server.name}</option>
							{/each}
						</select>
					</div>
				</label>

				<label class="flex flex-col gap-1.5 text-xs font-bold uppercase tracking-wide text-on-surface-variant">
					Database
					<div class="relative">
						<span class="material-symbols-outlined pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-on-surface-variant">
							database
						</span>
						<select
							value={databaseFilter}
							onchange={(event) => selectDatabaseFilter(eventValue(event))}
							class="h-11 w-full rounded-lg border border-outline-variant bg-surface-container-high py-2 pl-10 pr-8 text-sm font-medium text-on-surface outline-none focus:border-primary disabled:opacity-60"
							disabled={filteredDatabases.length === 0}
						>
							<option value="">All databases</option>
							{#each filteredDatabases as database}
								<option value={database.id}>{database.name}</option>
							{/each}
						</select>
					</div>
				</label>

				<div class="flex items-end gap-2">
					<button
						type="button"
						onclick={useCurrentContext}
						class="flex h-11 items-center gap-2 rounded-lg border border-outline-variant px-3 text-sm font-bold text-on-surface transition-colors hover:bg-surface-container-high"
					>
						<span class="material-symbols-outlined text-[18px]">my_location</span>
						Current
					</button>
					<button
						type="button"
						onclick={clearFilters}
						disabled={!hasFilters}
						class="flex h-11 items-center gap-2 rounded-lg border border-outline-variant px-3 text-sm font-bold text-on-surface transition-colors hover:bg-surface-container-high disabled:cursor-not-allowed disabled:opacity-40"
						aria-label="Clear filters"
					>
						<span class="material-symbols-outlined text-[18px]">filter_alt_off</span>
					</button>
				</div>
			</div>

			<div class="flex flex-wrap items-center gap-2 border-t border-outline-variant pt-3">
				<span class="text-xs font-bold uppercase tracking-wide text-on-surface-variant">Scope</span>
				<span class="inline-flex items-center gap-1 rounded-full bg-surface-container-high px-3 py-1 text-xs font-medium text-on-surface">
					<span class="material-symbols-outlined text-[14px]">dns</span>
					{activeServer?.name ?? 'All servers'}
				</span>
				<span class="inline-flex items-center gap-1 rounded-full bg-surface-container-high px-3 py-1 text-xs font-medium text-on-surface">
					<span class="material-symbols-outlined text-[14px]">database</span>
					{activeDatabase?.name ?? 'All databases'}
				</span>
				{#if searched}
					<span class="ml-auto text-xs text-on-surface-variant">{results.length} results</span>
				{/if}
			</div>
		</div>
	</section>

	{#if error}
		<div class="mb-4 rounded-lg border border-error/30 bg-error-container px-4 py-3 text-sm text-on-error-container">
			{error}
		</div>
	{/if}

	<section class="space-y-3">
		{#if searched && results.length > 0}
			<div class="flex flex-wrap items-center gap-2">
				{#each visibleResultCounts as item}
					<span class={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-bold ${typeTone(item.type)}`}>
						<span class="material-symbols-outlined text-[14px]">{typeIcon(item.type)}</span>
						{item.count} {typeLabel(item.type)}
					</span>
				{/each}
			</div>
		{/if}

		{#if !searched && !loading}
			<div class="rounded-lg border border-dashed border-outline-variant bg-surface-container px-6 py-14 text-center">
				<span class="material-symbols-outlined mb-3 text-[42px] text-primary">manage_search</span>
				<p class="font-bold text-on-surface">Search metadata</p>
			</div>
		{:else if searched && !loading && results.length === 0}
			<div class="rounded-lg border border-outline-variant bg-surface-container px-6 py-16 text-center">
				<span class="material-symbols-outlined mb-3 text-[40px] text-on-surface-variant">search_off</span>
				<p class="font-bold text-on-surface">No results found</p>
				<p class="text-sm text-on-surface-variant">Try a different term or remove filters.</p>
			</div>
		{:else}
			{#each results as result}
				<div
					class="group overflow-hidden rounded-lg border border-outline-variant bg-surface-container transition-colors hover:border-primary/30 hover:bg-surface-container-high"
				>
					<a href={resultHref(result)} class="grid gap-4 p-4 md:grid-cols-[auto_minmax(0,1fr)_auto]">
						<div class={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border ${typeTone(result.type)}`}>
							<span class="material-symbols-outlined">{typeIcon(result.type)}</span>
						</div>
						<div class="min-w-0">
							<div class="mb-1 flex flex-wrap items-center gap-2">
								<span class={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${typeTone(result.type)}`}>
									{typeLabel(result.type)}
								</span>
								{#if result.database_name}
									<span class="inline-flex items-center gap-1 text-xs text-on-surface-variant">
										<span class="material-symbols-outlined text-[14px]">database</span>
										{result.database_name}
									</span>
								{/if}
								{#if result.schema_name}
									<span class="inline-flex items-center gap-1 text-xs text-on-surface-variant">
										<span class="material-symbols-outlined text-[14px]">schema</span>
										{result.schema_name}
									</span>
								{/if}
							</div>
							<p class="mb-0.5 truncate font-bold text-on-surface group-hover:text-primary">{result.name}</p>
							{#if result.subtitle}
								<p class="mb-1 truncate text-sm text-on-surface-variant">{result.subtitle}</p>
							{/if}
							{#if result.description}
								<p class="line-clamp-2 text-sm leading-6 text-on-surface/80">{result.description}</p>
							{/if}
						</div>
						<div class="flex items-start gap-3">
							<span class="rounded-lg bg-surface-container-high px-2 py-1 text-xs font-bold text-on-surface-variant">
								{resultScore(result)}%
							</span>
							<span class="material-symbols-outlined text-on-surface-variant group-hover:text-primary">arrow_forward</span>
						</div>
					</a>

					<div class="flex flex-wrap items-center gap-2 border-t border-outline-variant px-4 py-3">
						<a
							href={docHref(result)}
							class="inline-flex items-center gap-1 rounded-full border border-outline-variant bg-surface-container-high px-2.5 py-1 text-[11px] font-medium text-on-surface transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
						>
							<span class="material-symbols-outlined text-[14px]">description</span>
							Doc
						</a>

						{#if hasSchemaView(result)}
							<a
								href={schemaViewHref(result)}
								class="inline-flex items-center gap-1 rounded-full border border-outline-variant bg-surface-container-high px-2.5 py-1 text-[11px] font-medium text-on-surface transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
							>
								<span class="material-symbols-outlined text-[14px]">schema</span>
								Schema view
							</a>
						{/if}

						{#if result.type === 'index'}
							<a
								href={indexAnalyticsHref(result)}
								class="inline-flex items-center gap-1 rounded-full border border-outline-variant bg-surface-container-high px-2.5 py-1 text-[11px] font-medium text-on-surface transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
							>
								<span class="material-symbols-outlined text-[14px]">speed</span>
								Index analytics
							</a>
						{/if}

						{#if result.type === 'table'}
							<a
								href={tableQueryAnalyticsHref(result)}
								class="inline-flex items-center gap-1 rounded-full border border-outline-variant bg-surface-container-high px-2.5 py-1 text-[11px] font-medium text-on-surface transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
							>
								<span class="material-symbols-outlined text-[14px]">search</span>
								Query analytics
							</a>
						{/if}

						{#each resultTags(result) as assignment}
							<span
								class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium"
								style="background-color: {assignment.tag.color || '#6366f1'}20; color: {assignment.tag.color || '#6366f1'}; border: 1px solid {assignment.tag.color || '#6366f1'}40;"
							>
								<span class="material-symbols-outlined text-[14px]">label</span>
								{assignment.tag.name}
							</span>
						{/each}
					</div>
				</div>
			{/each}
		{/if}
		{#if assignmentsLoading}
			<p class="text-xs text-on-surface-variant">Loading tags...</p>
		{/if}
	</section>
</div>
