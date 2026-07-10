<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';
	import { listDatabases, listServers, listRunHistory } from '$lib/api';
	import type { DatabaseListItem, RunHistoryItem, RunType, ServerListItem } from '$lib/api';

	
	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let selectedServer = $state('');
	let history = $state<RunHistoryItem[]>([]);
	let loading = $state(true);
	let error = $state('');
	let offset = $state(0);
	let filterStartedFrom = $state('');
	let filterStartedTo = $state('');
	let filterType = $state<RunType | ''>('');
	let filterStatus = $state('');
	let filterName = $state('');
	let filterMinDuration = $state('');
	let filterMaxDuration = $state('');
	const limit = 50;
	let serverDatabases = $derived(
		selectedServer ? databases.filter((database) => database.server_id === selectedServer) : databases
	);

	
	function typeBadge(type: RunType | null): string {
		if (type === 'server') return 'bg-secondary/10 text-secondary border-secondary/20';
		if (type === 'database') return 'bg-primary/10 text-primary border-primary/20';
		return 'bg-outline/10 text-on-surface-variant border-outline-variant/30';
	}

	function statusBadge(status: string): string {
		if (status === 'success') return 'bg-primary/10 text-primary border-primary/20';
		if (status === 'error') return 'bg-error/10 text-error border-error/20';
		return 'bg-outline/10 text-on-surface-variant border-outline-variant/30';
	}

	function formatTime(iso: string | null): string {
		if (!iso) return '--';
		const d = new Date(iso);
		if (Number.isNaN(d.getTime())) return '--';
		return d.toLocaleString();
	}

	function formatDuration(start: string | null, finish: string | null): string {
		if (!start || !finish) return '--';
		const ms = new Date(finish).getTime() - new Date(start).getTime();
		if (Number.isNaN(ms) || ms < 0) return '--';
		if (ms < 1000) return `${ms}ms`;
		const s = Math.floor(ms / 1000);
		if (s < 60) return `${s}s`;
		const m = Math.floor(s / 60);
		return `${m}m ${s % 60}s`;
	}

	function fromInputDate(value: string): string | undefined {
		if (!value) return undefined;
		return new Date(value).toISOString();
	}

	function optionalNumber(value: string): number | undefined {
		if (!value.trim()) return undefined;
		const parsed = Number(value);
		return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
	}

	function historyFilters() {
		return {
			runType: filterType || undefined,
			status: filterStatus || undefined,
			name: filterName.trim() || undefined,
			startedFrom: fromInputDate(filterStartedFrom),
			startedTo: fromInputDate(filterStartedTo),
			minDurationSeconds: optionalNumber(filterMinDuration),
			maxDurationSeconds: optionalNumber(filterMaxDuration)
		};
	}

	function eventValue(event: Event): string {
		return (event.currentTarget as HTMLSelectElement).value;
	}

	async function selectServer(serverId: string) {
		selectedServer = serverId;
		selectedServerId.set(serverId);
		const database = databases.find((item) => item.server_id === serverId);
		if (database && database.id !== selectedDb?.id) {
			await goto(`/runs/${database.id}/history`, { replaceState: true });
			await loadDatabaseHistory(database);
		}
	}

	async function loadDatabaseHistory(db: DatabaseListItem, resetOffset = true) {
		selectedDb = db;
		selectedDatabaseId.set(db.id);
		selectedServer = db.server_id;
		selectedServerId.set(db.server_id);
		if (resetOffset) offset = 0;
		loading = true;
		error = '';
		try {
			history = await listRunHistory(db.id, limit, offset, historyFilters());
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load run history.';
			history = [];
		} finally {
			loading = false;
		}
	}

	async function changePage(delta: number) {
		const nextOffset = Math.max(0, offset + delta * limit);
		if (!selectedDb || nextOffset === offset) return;
		offset = nextOffset;
		await loadDatabaseHistory(selectedDb, false);
	}

	async function applyFilters() {
		if (!selectedDb) return;
		offset = 0;
		await loadDatabaseHistory(selectedDb, false);
	}

	async function clearFilters() {
		filterStartedFrom = '';
		filterStartedTo = '';
		filterType = '';
		filterStatus = '';
		filterName = '';
		filterMinDuration = '';
		filterMaxDuration = '';
		await applyFilters();
	}

	async function load() {
		try {
			loading = true;
			error = '';
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			if (databases.length === 0) {
				history = [];
				return;
			}

			const routeDbId = $page.params.database_id;
			const db = databases.find((d) => d.id === routeDbId) ?? databases[0];
			if (db.id !== routeDbId) {
				await goto(`/runs/${db.id}/history`, { replaceState: true });
				return;
			}
			await loadDatabaseHistory(db);
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
</script>


<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">history</span>
		<h1 class="font-headline-md text-headline-md text-on-background m-0">Run History</h1>
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
				Connect a database from the Servers page to view collector run history.
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
						if (database) {
							goto(`/runs/${database.id}/history`, { replaceState: true });
							loadDatabaseHistory(database);
						}
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
				<label class="flex flex-col gap-2">
					<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">From</span>
					<input
						type="datetime-local"
						bind:value={filterStartedFrom}
						class="h-9 rounded-lg border border-outline-variant bg-surface-container-high px-3 text-xs text-on-surface outline-none focus:border-primary"
					/>
				</label>
				<label class="flex flex-col gap-2">
					<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">To</span>
					<input
						type="datetime-local"
						bind:value={filterStartedTo}
						class="h-9 rounded-lg border border-outline-variant bg-surface-container-high px-3 text-xs text-on-surface outline-none focus:border-primary"
					/>
				</label>
				<label class="flex flex-col gap-2">
					<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Type</span>
					<select
						bind:value={filterType}
						class="h-9 cursor-pointer rounded-lg border border-outline-variant bg-surface-container-high px-3 text-xs font-bold text-on-surface outline-none focus:border-primary"
					>
						<option value="">All types</option>
						<option value="server">Server</option>
						<option value="database">Database</option>
					</select>
				</label>
				<label class="flex flex-col gap-2">
					<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Status</span>
					<select
						bind:value={filterStatus}
						class="h-9 cursor-pointer rounded-lg border border-outline-variant bg-surface-container-high px-3 text-xs font-bold text-on-surface outline-none focus:border-primary"
					>
						<option value="">All status</option>
						<option value="success">Success</option>
						<option value="error">Error</option>
						<option value="running">Running</option>
					</select>
				</label>
				<label class="flex min-w-48 flex-col gap-2">
					<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Name</span>
					<input
						type="search"
						bind:value={filterName}
						placeholder="Collector name"
						class="h-9 rounded-lg border border-outline-variant bg-surface-container-high px-3 text-xs text-on-surface outline-none placeholder:text-on-surface-variant focus:border-primary"
					/>
				</label>
				<label class="flex w-32 flex-col gap-2">
					<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Min sec</span>
					<input
						type="number"
						min="0"
						bind:value={filterMinDuration}
						class="h-9 rounded-lg border border-outline-variant bg-surface-container-high px-3 text-xs text-on-surface outline-none focus:border-primary"
					/>
				</label>
				<label class="flex w-32 flex-col gap-2">
					<span class="font-label-caps text-[10px] uppercase tracking-widest text-on-surface-variant">Max sec</span>
					<input
						type="number"
						min="0"
						bind:value={filterMaxDuration}
						class="h-9 rounded-lg border border-outline-variant bg-surface-container-high px-3 text-xs text-on-surface outline-none focus:border-primary"
					/>
				</label>
				<button
					onclick={applyFilters}
					disabled={loading}
					class="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-xs font-bold text-on-primary transition-all hover:bg-primary/90 disabled:opacity-50"
				>
					<span class="material-symbols-outlined text-[16px]">search</span>
					Search
				</button>
				<button
					onclick={clearFilters}
					disabled={loading}
					class="flex h-9 items-center gap-2 rounded-lg border border-outline-variant bg-surface-container px-3 text-xs font-bold text-on-surface transition-all hover:bg-surface-variant disabled:opacity-50"
				>
					<span class="material-symbols-outlined text-[16px]">filter_alt_off</span>
				</button>
			</div>
		</section>

		
		<section class="overflow-hidden rounded-lg border border-outline-variant bg-surface-container">
			<div
				class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3"
			>
				<div class="flex items-center gap-2">
					<span class="material-symbols-outlined text-sm text-primary">history</span>
					<h2 class="m-0 font-headline-md text-headline-md">Execution History</h2>
				</div>
				<span class="font-code-sm text-code-sm text-on-surface-variant">
					{history.length} runs
				</span>
			</div>

			<div class="overflow-x-auto">
				<table class="w-full text-left border-collapse">
					<thead class="bg-surface-container-high">
						<tr>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>NAME</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>TYPE</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>STATUS</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>STARTED</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>DURATION</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>ERRORS</th
							>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-variant/20">
						{#if loading}
							<tr>
								<td colspan="6" class="px-4 py-8 text-center text-on-surface-variant text-sm">
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
										Loading history…
									</div>
								</td>
							</tr>
						{:else if history.length === 0}
							<tr>
								<td colspan="6" class="px-4 py-8 text-center text-on-surface-variant text-sm">
									No run history found for this database.
								</td>
							</tr>
						{:else}
							{#each history as run (run.id)}
								<tr class="hover:bg-surface-variant/20 transition-colors">
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface font-bold"
										>{run.name || '--'}</td
									>
									<td class="px-4 py-3">
										<span
											class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border {typeBadge(
												run.type
											)}"
										>
											{run.type || 'unknown'}
										</span>
									</td>
									<td class="px-4 py-3">
										<span
											class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold border {statusBadge(
												run.status
											)}"
										>
											{run.status}
										</span>
									</td>
									<td class="px-4 py-3 text-sm text-on-surface-variant"
										>{formatTime(run.started_at)}</td
									>
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface"
										>{formatDuration(run.started_at, run.finished_at)}</td
									>
									<td class="px-4 py-3 text-sm">
										{#if run.errors && run.errors.length > 0}
											<span class="text-error" title={run.errors.join('\n')}>
												{run.errors.length} error{run.errors.length !== 1 ? 's' : ''}
											</span>
										{:else}
											<span class="text-on-surface-variant">--</span>
										{/if}
									</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			</div>

			
			<div class="flex items-center justify-between border-t border-outline-variant px-4 py-3">
				<button
					onclick={() => changePage(-1)}
					disabled={offset === 0 || loading}
					class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-on-surface text-xs font-bold hover:bg-surface-variant disabled:opacity-50 cursor-pointer"
				>
					<span class="material-symbols-outlined text-[14px]">chevron_left</span>
					Previous
				</button>
				<span class="text-xs text-on-surface-variant font-code-sm">
					Page {Math.floor(offset / limit) + 1}
				</span>
				<button
					onclick={() => changePage(1)}
					disabled={history.length < limit || loading}
					class="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-outline-variant bg-surface-container text-on-surface text-xs font-bold hover:bg-surface-variant disabled:opacity-50 cursor-pointer"
				>
					Next
					<span class="material-symbols-outlined text-[14px]">chevron_right</span>
				</button>
			</div>
		</section>
	{/if}
</div>
