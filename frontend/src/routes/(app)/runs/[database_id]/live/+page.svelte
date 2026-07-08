<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';
	import { listDatabases, listServers, createRunEventSource, controlRun } from '$lib/api';
	import type { DatabaseListItem, RunItem, RunAction, RunType, ServerListItem } from '$lib/api';

	// ── State ────────────────────────────────────────────────────────────────────
	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let selectedServer = $state('');
	let runs = $state<RunItem[] | null>(null);
	let loading = $state(true);
	let error = $state('');
	let eventSource = $state<EventSource | null>(null);
	let controlling = $state<Set<string>>(new Set());
	let showStatusHelp = $state(false);
	let serverDatabases = $derived(
		selectedServer ? databases.filter((database) => database.server_id === selectedServer) : databases
	);

	// ── Helpers ──────────────────────────────────────────────────────────────────
	function statusColor(status: string): string {
		if (status === 'running') return 'text-primary';
		if (status === 'paused') return 'text-tertiary';
		if (status === 'idle') return 'text-on-surface-variant';
		return 'text-error';
	}

	function statusBadge(status: string): string {
		if (status === 'running') return 'bg-primary/10 text-primary border-primary/20';
		if (status === 'paused') return 'bg-tertiary/10 text-tertiary border-tertiary/20';
		if (status === 'idle') return 'bg-outline/10 text-on-surface-variant border-outline-variant/30';
		return 'bg-error/10 text-error border-error/20';
	}

	function typeBadge(type: RunType): string {
		return type === 'server'
			? 'bg-secondary/10 text-secondary border-secondary/20'
			: 'bg-primary/10 text-primary border-primary/20';
	}

	function formatDuration(ms: number): string {
		const absMs = Math.abs(ms);
		const s = Math.floor(absMs / 1000);
		if (s < 60) return `${s}s`;
		const m = Math.floor(s / 60);
		if (m < 60) return `${m}m ${s % 60}s`;
		const h = Math.floor(m / 60);
		if (h < 24) return `${h}h ${m % 60}m`;
		const d = Math.floor(h / 24);
		return `${d}d ${h % 24}h`;
	}

	function formatNextRun(iso: string | null): string {
		if (!iso) return '--';
		const ms = new Date(iso).getTime() - Date.now();
		if (Number.isNaN(ms)) return '--';
		if (ms <= 0) return 'due now';
		return `in ${formatDuration(ms)}`;
	}

	function formatRunningTime(iso: string | null, status: string): string {
		if (!iso || status !== 'running') return '--';
		const ms = Date.now() - new Date(iso).getTime();
		if (Number.isNaN(ms) || ms < 0) return '--';
		return formatDuration(ms);
	}

	function controlKey(r: RunItem): string {
		return `${r.type}:${r.id}`;
	}

	function eventValue(event: Event): string {
		return (event.currentTarget as HTMLSelectElement).value;
	}

	async function selectServer(serverId: string) {
		selectedServer = serverId;
		selectedServerId.set(serverId);
		const database = databases.find((item) => item.server_id === serverId);
		if (database && database.id !== selectedDb?.id) {
			await goto(`/runs/${database.id}/live`, { replaceState: true });
			await selectDatabase(database);
		}
	}

	async function handleControl(r: RunItem, action: RunAction) {
		if (!selectedDb) return;
		const key = controlKey(r);
		controlling = new Set([...controlling, key]);
		try {
			await controlRun(selectedDb.id, r.id, r.type, action);
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || `Failed to ${action} run.`;
		} finally {
			const next = new Set(controlling);
			next.delete(key);
			controlling = next;
		}
	}

	function connectStream(databaseId: string) {
		if (eventSource) eventSource.close();
		runs = null;
		const es = createRunEventSource(databaseId);
		es.addEventListener('runs', (event) => {
			try {
				runs = JSON.parse((event as MessageEvent).data);
			} catch {
				/* ignore */
			}
		});
		es.onerror = () => {
			/* browser auto-reconnects */
		};
		eventSource = es;
	}

	async function selectDatabase(db: DatabaseListItem) {
		selectedDb = db;
		selectedDatabaseId.set(db.id);
		selectedServer = db.server_id;
		selectedServerId.set(db.server_id);
		error = '';
		connectStream(db.id);
	}

	async function load() {
		try {
			loading = true;
			error = '';
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);

			if (databases.length === 0) {
				return;
			}

			const routeDbId = $page.params.database_id;
			const db = databases.find((d) => d.id === routeDbId) ?? databases[0];
			if (db.id !== routeDbId) {
				await goto(`/runs/${db.id}/live`, { replaceState: true });
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
	onDestroy(() => {
		if (eventSource) eventSource.close();
	});
</script>

<!-- ── Top Bar ─────────────────────────────────────────────────────────────── -->
<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">precision_manufacturing</span>
		<h1 class="font-headline-md text-headline-md text-on-background m-0">Runs</h1>
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
		<div
			class="mb-6 p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
		>
			<span class="material-symbols-outlined text-error">error</span>
			<p class="font-code-sm text-sm text-error">{error}</p>
		</div>
	{/if}

	{#if loading}
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
				Connect a database from the Servers page to monitor collector runs.
			</p>
		</div>
	{:else}
		<!-- Database selector -->
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
							goto(`/runs/${database.id}/live`, { replaceState: true });
							selectDatabase(database);
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

		<!-- Run table -->
		<section class="overflow-hidden rounded-lg border border-outline-variant bg-surface-container">
			<div
				class="flex items-center justify-between border-b border-outline-variant bg-surface-container-low px-4 py-3"
			>
				<div class="flex items-center gap-2">
					<span class="material-symbols-outlined text-sm text-primary">precision_manufacturing</span
					>
					<h2 class="m-0 font-headline-md text-headline-md">Live Runs</h2>
					<div class="relative">
						<button
							onclick={() => (showStatusHelp = !showStatusHelp)}
							class="text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
							aria-label="Status help"
						>
							<span class="material-symbols-outlined text-[16px]">help_outline</span>
						</button>
						{#if showStatusHelp}
							<div
								class="absolute left-0 top-full mt-2 z-50 w-64 rounded-lg border border-outline-variant bg-surface-container-high p-3 text-xs shadow-lg"
							>
								<p class="font-bold text-on-surface mb-2">Run statuses</p>
								<ul class="space-y-1.5 text-on-surface-variant">
									<li>
										<span class="font-bold text-on-surface">Idle:</span> waiting for the next scheduled
										run.
									</li>
									<li>
										<span class="font-bold text-on-surface">Running:</span> the collector is actively
										executing right now.
									</li>
									<li>
										<span class="font-bold text-on-surface">Paused:</span> temporarily suspended in
										settings.
									</li>
									<li>
										<span class="font-bold text-on-surface">Stopped:</span> execution halted for a
										running collector.
									</li>
								</ul>
							</div>
						{/if}
					</div>
				</div>
				<span class="font-code-sm text-code-sm text-on-surface-variant">
					SSE updates every 2s
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
								>SCOPE</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>INTERVAL</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>STATUS</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>RUNNING TIME</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
								>NEXT RUN</th
							>
							<th
								class="px-4 py-3 font-label-caps text-on-surface-variant text-[10px] tracking-widest text-right"
								>ACTIONS</th
							>
						</tr>
					</thead>
					<tbody class="divide-y divide-outline-variant/20">
						{#if runs === null}
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
										Connecting to run stream…
									</div>
								</td>
							</tr>
						{:else if runs.length === 0}
							<tr>
								<td colspan="8" class="px-4 py-8 text-center text-on-surface-variant text-sm">
									No collector runs found for this database.
								</td>
							</tr>
						{:else}
							{#each runs as run (run.id + ':' + run.type)}
								{@const key = controlKey(run)}
								{@const busy = controlling.has(key)}
								<tr class="hover:bg-surface-variant/20 transition-colors">
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface font-bold"
										>{run.name}</td
									>
									<td class="px-4 py-3">
										<span
											class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border {typeBadge(
												run.type
											)}"
										>
											{run.type}
										</span>
									</td>
									<td class="px-4 py-3 text-sm text-on-surface-variant">
										{#if run.database_name}
											{run.database_name}
										{:else}
											<span class="text-on-surface-variant">server-wide</span>
										{/if}
									</td>
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface"
										>{run.interval}s</td
									>
									<td class="px-4 py-3">
										<span
											class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold border {statusBadge(
												run.status
											)}"
										>
											<span class="w-1.5 h-1.5 rounded-full bg-current"></span>
											{run.status}
										</span>
									</td>
									<td class="px-4 py-3 font-code-sm text-code-sm {statusColor(run.status)}">
										{formatRunningTime(run.next_run_at, run.status)}
									</td>
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant">
										{formatNextRun(run.next_run_at)}
									</td>
									<td class="px-4 py-3 text-right">
										<div class="flex items-center justify-end gap-2">
											<button
												onclick={() => handleControl(run, 'force_run')}
												disabled={busy || run.is_paused}
												class="flex items-center gap-1 px-2 py-1 rounded bg-primary/10 text-primary border border-primary/20 text-[10px] font-bold hover:bg-primary/20 disabled:opacity-50 cursor-pointer"
												title={run.is_paused ? 'Cannot force run while paused' : 'Run now'}
											>
												<span class="material-symbols-outlined text-[12px]">bolt</span>
												Run now
											</button>
											<button
												onclick={() => handleControl(run, 'stop')}
												disabled={busy || run.status !== 'running'}
												class="flex items-center gap-1 px-2 py-1 rounded bg-error/10 text-error border border-error/20 text-[10px] font-bold hover:bg-error/20 disabled:opacity-50 cursor-pointer"
												title={run.status !== 'running'
													? 'Stop is only available while running'
													: 'Stop execution'}
											>
												<span class="material-symbols-outlined text-[12px]">stop</span>
												Stop
											</button>
											<button
												onclick={() => handleControl(run, 'delete')}
												disabled={busy}
												class="flex items-center gap-1 px-2 py-1 rounded bg-surface-variant text-on-surface-variant border border-outline-variant text-[10px] font-bold hover:bg-error/10 hover:text-error hover:border-error/20 disabled:opacity-50 cursor-pointer"
											>
												<span class="material-symbols-outlined text-[12px]">delete</span>
											</button>
										</div>
									</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			</div>
		</section>
	{/if}
</div>
