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
	let searchHelpOpen = $state(false);

	let filterModalOpen = $state(false);
	let selectedTypes = $state<string[]>([]);
	const availableTypes = ['database', 'schema', 'table', 'column', 'index', 'tag'];

	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let assignments = $state<TagAssignment[]>([]);
	let assignmentsLoading = $state(false);
	let selectedServer = $state('');
	let selectedDbId = $state('');
	const serverDatabases = $derived(
		selectedServer
			? databases.filter((database) => database.server_id === selectedServer)
			: databases
	);
	const filteredResults = $derived(
		selectedTypes.length > 0 ? results.filter((r) => selectedTypes.includes(r.type)) : results
	);

	const visibleResultCounts = $derived.by(() => {
		const counts = new Map<MetadataSearchResult['type'], number>();
		for (const result of filteredResults) {
			counts.set(result.type, (counts.get(result.type) ?? 0) + 1);
		}
		return Array.from(counts.entries()).map(([type, count]) => ({ type, count }));
	});

	onMount(async () => {
		try {
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			const dbId = $page.url.searchParams.get('database_id') ?? $selectedDatabaseId ?? databases[0]?.id;
			if (dbId) {
				await selectDatabase(dbId);
			} else if (servers.length > 0) {
				selectedServer = servers[0].id;
				selectedServerId.set(servers[0].id);
			}
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

	function eventValue(event: Event): string {
		return (event.currentTarget as HTMLSelectElement).value;
	}

	async function selectServer(serverId: string) {
		selectedServer = serverId;
		selectedServerId.set(serverId);
		const database = databases.find((item) => item.server_id === serverId);
		if (database && database.id !== selectedDbId) {
			await selectDatabase(database.id);
		}
	}

	async function selectDatabase(dbId: string) {
		selectedDbId = dbId;
		const database = databases.find((item) => item.id === dbId);
		if (database) {
			selectedDatabaseId.set(dbId);
			selectedServer = database.server_id;
			selectedServerId.set(database.server_id);
		}
		if (query.trim()) await runSearch(true);
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
				server_id: selectedServer || undefined,
				database_id: selectedDbId || undefined,
				limit: 25,
				semantic
			});
			if (requestId !== searchRequestId) return;
			results = response.results;
			loadTagsForResults(response.results);

			const params = new URLSearchParams();
			params.set('q', term);
			if (selectedServer) params.set('server_id', selectedServer);
			if (selectedDbId) params.set('database_id', selectedDbId);
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

	function scoreTone(result: MetadataSearchResult): string {
		const pct = resultScore(result);
		if (pct >= 75) return 'text-status-healthy bg-status-healthy/10 border-status-healthy/20';
		if (pct >= 50) return 'text-status-warning bg-status-warning/10 border-status-warning/20';
		return 'text-on-surface-variant bg-surface-container-high border-outline-variant';
	}
</script>

<header
	class="fixed top-0 right-0 z-40 flex h-16 w-[calc(100%-16rem)] items-center justify-between border-b border-outline-variant bg-surface-dim px-container-padding"
>
	<div class="flex items-center gap-4">
		<span class="material-symbols-outlined text-primary">search</span>
		<div class="flex items-center gap-3">
			<h1 class="m-0 font-headline-md text-headline-md text-on-background">Search</h1>
			<div class="relative">
				<button
					onclick={() => (searchHelpOpen = !searchHelpOpen)}
					onmouseenter={() => (searchHelpOpen = true)}
					onmouseleave={() => (searchHelpOpen = false)}
					class="flex h-6 w-6 cursor-pointer items-center justify-center rounded-full border border-outline-variant text-on-surface-variant transition-colors hover:border-primary/40 hover:text-primary"
					aria-label="Search page explanation"
				>
					<span class="material-symbols-outlined text-[14px]">help</span>
				</button>
				{#if searchHelpOpen}
					<div
						class="absolute left-0 top-full z-50 mt-2 w-80 rounded-lg border border-outline-variant bg-surface-container-high p-3 text-xs text-on-surface shadow-lg"
					>
						<p class="mb-1 font-bold">What is this page?</p>
						<p class="mb-2 text-on-surface-variant">
							Semantic search across all monitored metadata — tables, columns, indexes, views and
							schemas. Results are ranked by similarity to your query.
						</p>
						<p class="font-bold">Tips</p>
						<p class="text-on-surface-variant">
							Use the server/database selectors to narrow the scope. The match score indicates how
							closely each result relates to your search term.
						</p>
					</div>
				{/if}
			</div>
		</div>
	</div>
	{#if searched}
		<span
			class="rounded-full border border-outline-variant bg-surface-container px-3 py-1 font-label-caps text-[10px] text-on-surface-variant"
		>
			{filteredResults.length} results
		</span>
	{/if}
</header>

<div class="px-container-padding pt-24 pb-12">
	<section class="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end">
		<div
			class="flex min-h-12 flex-1 items-center gap-3 rounded-lg border border-outline-variant bg-surface-container px-4 transition-colors focus-within:border-primary"
		>
			<span class="material-symbols-outlined text-[20px] text-primary">search</span>
			<input
				type="text"
				bind:value={query}
				oninput={onInputSearch}
				onkeydown={onInputKeydown}
				placeholder="Search tables, columns, indexes, schemas…"
				class="min-w-0 flex-1 bg-transparent text-base text-on-surface outline-none placeholder:text-on-surface-variant/60"
			/>
			{#if loading}
				<span class="material-symbols-outlined animate-spin text-on-surface-variant">progress_activity</span>
			{/if}
		</div>

		<div class="flex flex-wrap items-center gap-3">
			<button
				type="button"
				onclick={() => (filterModalOpen = true)}
				class="flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-outline-variant bg-surface-container px-3 text-xs font-bold text-on-surface transition-colors hover:border-primary/40 hover:text-primary"
			>
				<span class="material-symbols-outlined text-[16px]">filter_list</span>
				Filter
				{#if selectedTypes.length > 0}
					<span class="ml-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary/20 px-1 text-[10px] font-bold text-primary">
						{selectedTypes.length}
					</span>
				{/if}
			</button>

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
					value={selectedDbId}
					onchange={(event) => selectDatabase(eventValue(event))}
					disabled={serverDatabases.length <= 1}
					class="cursor-pointer rounded-lg border border-secondary/30 bg-secondary/10 px-3 py-1.5 text-xs font-bold text-secondary outline-none transition-all hover:bg-secondary/15 focus:border-secondary disabled:cursor-default disabled:opacity-80"
				>
					{#each serverDatabases as database}
						<option value={database.id}>{database.name}</option>
					{/each}
				</select>
			</label>
		</div>
	</section>

	{#if error}
		<div class="mb-4 rounded-lg border border-error/30 bg-error-container px-4 py-3 text-sm text-on-error-container">
			{error}
		</div>
	{/if}

	<section class="space-y-3">
		{#if searched && filteredResults.length > 0}
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
			<div class="rounded-lg border border-outline-variant bg-surface-container p-6">
				<div class="mb-5 flex items-center gap-2">
					<span class="material-symbols-outlined text-[20px] text-primary">lightbulb</span>
					<h2 class="m-0 font-headline-md text-base font-bold text-on-surface">Suggested searches</h2>
				</div>
				<p class="mb-4 text-sm text-on-surface-variant">Click a term to start, or type your own query above.</p>
				<div class="flex flex-wrap gap-2">
					{#each ['primary key', 'foreign key', 'timestamp', 'user', 'email', 'uuid', 'jsonb', 'created_at'] as term}
						<button
							type="button"
							onclick={() => { query = term; runSearch(true); }}
							class="cursor-pointer rounded-lg border border-outline-variant bg-surface-container-high px-3 py-1.5 text-xs font-medium text-on-surface transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
						>
							<span class="material-symbols-outlined mr-1 text-[14px] align-middle">tag</span>
							{term}
						</button>
					{/each}
				</div>
			</div>
		{:else if searched && !loading && filteredResults.length === 0}
			<div class="rounded-lg border border-outline-variant bg-surface-container px-6 py-16 text-center">
				<span class="material-symbols-outlined mb-3 text-[40px] text-on-surface-variant">search_off</span>
				<p class="font-bold text-on-surface">No results found</p>
				<p class="text-sm text-on-surface-variant">Try a different term or remove filters.</p>
			</div>
		{:else}
			{#each filteredResults as result}
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
						<div class="flex flex-col items-end gap-1">
						<div class="flex flex-col items-center gap-0.5">
							<span class={`rounded-lg border px-2.5 py-1 font-mono text-sm font-bold tabular-nums ${scoreTone(result)}`}>
								{resultScore(result)}%
							</span>
							<span class="text-[9px] font-bold uppercase tracking-wider text-on-surface-variant">Match</span>
						</div>
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

{#if filterModalOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-background/80 px-4 backdrop-blur-sm"
		onclick={(e) => { if (e.target === e.currentTarget) filterModalOpen = false; }}
	>
		<div class="w-full max-w-md rounded-2xl border border-outline-variant bg-surface-container-high p-6 shadow-xl">
			<div class="mb-6 flex items-center justify-between">
				<h2 class="m-0 font-headline-sm text-on-surface">Filter by Type</h2>
				<button
					type="button"
					class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full text-on-surface-variant transition-colors hover:bg-surface-container-highest hover:text-on-surface"
					onclick={() => (filterModalOpen = false)}
				>
					<span class="material-symbols-outlined">close</span>
				</button>
			</div>

			<div class="mb-6 grid grid-cols-2 gap-3">
				{#each availableTypes as type}
					<label class="flex cursor-pointer items-center gap-3 rounded-lg border border-outline-variant bg-surface-container p-3 transition-colors hover:border-primary/40 has-[:checked]:border-primary has-[:checked]:bg-primary/5">
						<input
							type="checkbox"
							bind:group={selectedTypes}
							value={type}
							class="h-4 w-4 cursor-pointer rounded border-outline-variant text-primary focus:ring-primary focus:ring-offset-surface-container"
						/>
						<div class="flex items-center gap-2">
							<span class={`material-symbols-outlined text-[18px] ${typeTone(type as any).split(' ')[1]}`}>{typeIcon(type as any)}</span>
							<span class="text-sm font-medium text-on-surface">{typeLabel(type as any)}</span>
						</div>
					</label>
				{/each}
			</div>

			<div class="flex justify-end gap-3">
				<button
					type="button"
					class="cursor-pointer rounded-lg px-4 py-2 text-sm font-bold text-on-surface-variant transition-colors hover:bg-surface-container-highest hover:text-on-surface"
					onclick={() => { selectedTypes = []; }}
				>
					Clear All
				</button>
				<button
					type="button"
					class="cursor-pointer rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary transition-colors hover:bg-primary/90"
					onclick={() => (filterModalOpen = false)}
				>
					Apply Filters
				</button>
			</div>
		</div>
	</div>
{/if}
