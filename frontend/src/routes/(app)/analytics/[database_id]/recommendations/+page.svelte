<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';
	import {
		getAnalyticsRecommendations,
		patchAnalyticsRecommendation,
		listDatabases,
		listServers
	} from '$lib/api';
	import type {
		AnalyticsRecommendation,
		AnalyticsRecommendationStatus,
		DatabaseListItem,
		ServerListItem
	} from '$lib/api';
	import RecommendationCard from './RecommendationCard.svelte';

	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let selectedServer = $state('');

	let items = $state<AnalyticsRecommendation[]>([]);
	let loading = $state(true);
	let error = $state('');
	let status = $state<AnalyticsRecommendationStatus | 'all'>('open');
	let updating = $state<Set<number>>(new Set());
	let expandedEvidenceId = $state<number | null>(null);

	const databaseId = $derived($page.params.database_id ?? '');

	let serverDatabases = $derived(
		selectedServer
			? databases.filter((database) => database.server_id === selectedServer)
			: databases
	);

	const counts = $derived({
		total: items.length,
		critical: items.filter((item) => item.severity === 'critical').length,
		warning: items.filter((item) => item.severity === 'warning').length,
		info: items.filter((item) => item.severity === 'info').length
	});

	const statuses: { value: AnalyticsRecommendationStatus | 'all'; label: string }[] = [
		{ value: 'open', label: 'Open' },
		{ value: 'dismissed', label: 'Dismissed' },
		{ value: 'resolved', label: 'Resolved' },
		{ value: 'all', label: 'All' }
	];

	async function loadData(database: DatabaseListItem) {
		selectedDb = database;
		selectedDatabaseId.set(database.id);
		selectedServer = database.server_id;
		selectedServerId.set(database.server_id);
		loading = true;
		error = '';
		try {
			items = await getAnalyticsRecommendations(database.id, status);
		} catch (loadError) {
			if (loadError instanceof Error && loadError.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = loadError instanceof Error ? loadError.message : 'Failed to load recommendations.';
		} finally {
			loading = false;
		}
	}

	async function update(item: AnalyticsRecommendation, nextStatus: AnalyticsRecommendationStatus) {
		if (!selectedDb) return;
		updating = new Set([...updating, item.id]);
		error = '';
		try {
			const updated = await patchAnalyticsRecommendation(selectedDb.id, item.id, nextStatus);
			items = items.map((entry) => (entry.id === updated.id ? updated : entry));
			if (status !== 'all' && status !== nextStatus) {
				items = items.filter((entry) => entry.id !== item.id);
			}
		} catch (updateError) {
			error =
				updateError instanceof Error ? updateError.message : 'Failed to update recommendation.';
		} finally {
			const next = new Set(updating);
			next.delete(item.id);
			updating = next;
		}
	}

	function selectStatus(nextStatus: AnalyticsRecommendationStatus | 'all') {
		if (status === nextStatus) return;
		status = nextStatus;
		if (selectedDb) {
			void loadData(selectedDb);
		}
	}

	function toggleEvidence(itemId: number, isOpen: boolean) {
		expandedEvidenceId = isOpen ? itemId : null;
	}

	async function load() {
		loading = true;
		error = '';
		try {
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			if (databases.length === 0) {
				return;
			}

			const routeDbId = $page.params.database_id;
			const db = databases.find((d) => d.id === routeDbId) ?? databases[0];
			if (db.id !== routeDbId) {
				await goto(`/analytics/${db.id}/recommendations`, { replaceState: true });
				return;
			}
			await loadData(db);
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

	onMount(() => void load());
</script>

<!-- Fixed Header -->
<header
	class="fixed top-0 right-0 app-page-header z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">tips_and_updates</span>
		<h1 class="font-headline-md text-headline-md text-on-background m-0">Analytics</h1>
		<span class="font-label-caps text-[10px] text-on-surface-variant">/ Recommendations</span>
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
				Connect a database from the Servers page to view analytics.
			</p>
		</div>
	{:else}
		<div class="mb-6 flex flex-wrap items-center justify-between gap-3">
			<div
				class="flex max-w-full items-center gap-2 overflow-x-auto rounded-xl border border-outline-variant bg-surface-container p-1"
			>
				{#each statuses as option}
					<button
						onclick={() => selectStatus(option.value)}
						class="shrink-0 rounded-lg px-3 py-2 text-xs font-bold transition {status ===
						option.value
							? 'bg-primary text-on-primary shadow-sm'
							: 'text-on-surface-variant hover:bg-surface-container-highest'}"
					>
						{option.label}
					</button>
				{/each}
			</div>
		</div>

		<div class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
			<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
				<div class="text-2xl font-bold text-on-surface">{counts.total}</div>
				<div class="mt-1 text-xs font-bold uppercase tracking-wide text-on-surface-variant">
					Displayed
				</div>
			</div>
			<div class="rounded-xl border border-error/25 bg-error/5 p-4">
				<div class="text-2xl font-bold text-error">{counts.critical}</div>
				<div class="mt-1 text-xs font-bold uppercase tracking-wide text-error">Critical</div>
			</div>
			<div class="rounded-xl border border-tertiary/25 bg-tertiary/5 p-4">
				<div class="text-2xl font-bold text-tertiary">{counts.warning}</div>
				<div class="mt-1 text-xs font-bold uppercase tracking-wide text-tertiary">Warning</div>
			</div>
			<div class="rounded-xl border border-primary/20 bg-primary/5 p-4">
				<div class="text-2xl font-bold text-primary">{counts.info}</div>
				<div class="mt-1 text-xs font-bold uppercase tracking-wide text-primary">Information</div>
			</div>
		</div>

		{#if loading}
			<div class="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
				{#each [1, 2, 3] as placeholder}
					<div
						class="h-72 animate-pulse rounded-xl border border-outline-variant bg-surface-container"
						aria-hidden="true"
					>
						<div class="h-1 rounded-t-xl bg-primary/20"></div>
						<div class="space-y-4 p-5">
							<div class="h-9 w-3/4 rounded bg-surface-container-highest"></div>
							<div class="h-4 w-full rounded bg-surface-container-highest"></div>
							<div class="h-20 rounded bg-surface-container-highest"></div>
						</div>
					</div>
				{/each}
			</div>
		{:else if items.length === 0}
			<div
				class="rounded-xl border border-dashed border-outline-variant bg-surface-container p-10 text-center"
			>
				<span class="material-symbols-outlined text-4xl text-primary">tips_and_updates</span>
				<h2 class="mt-3 font-headline-md">
					No {status === 'all' ? '' : status} recommendations
				</h2>
				<p class="text-sm text-on-surface-variant">
					Run Analytics after enough metric data has been collected to generate findings.
				</p>
			</div>
		{:else}
			<div class="grid items-stretch gap-4 lg:grid-cols-2 2xl:grid-cols-3">
				{#each items as item (item.id)}
					<RecommendationCard
						{item}
						busy={updating.has(item.id)}
						databaseId={selectedDb?.id ?? databaseId}
						onUpdate={(nextStatus) => update(item, nextStatus)}
						evidenceOpen={expandedEvidenceId === item.id}
						onEvidenceToggle={(isOpen) => toggleEvidence(item.id, isOpen)}
					/>
				{/each}
			</div>
		{/if}
	{/if}
</div>
