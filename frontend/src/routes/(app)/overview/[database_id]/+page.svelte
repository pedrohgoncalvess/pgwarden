<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import {
		listDatabases,
		getDatabaseStats,
		getDatabaseUptime,
		createTpsEventSource,
		formatBytes,
		listServers,
		testConnection,
		createServer,
		createDatabase,
		createSessionEventSource,
		createLockEventSource,
		createServerMetricsEventSource,
		createNativeQueryEventSource
	} from '$lib/api';
	import type {
		DatabaseListItem,
		DatabaseStats,
		UptimeResponse,
		ServerListItem,
		ServerCreatedResponse,
		SessionMetric,
		LockMetric,
		CpuMetric,
		RamMetric,
		NativeQueryMetric
	} from '$lib/api';

	let databases = $state<DatabaseListItem[]>([]);
	let selectedDb = $state<DatabaseListItem | null>(null);
	let stats = $state<DatabaseStats | null>(null);
	let uptime = $state<UptimeResponse | null>(null);
	let tps = $state<number>(0);
	let sessions = $state<SessionMetric[] | null>(null);
	let nativeQueries = $state<NativeQueryMetric[] | null>(null);
	let locks = $state<LockMetric[] | null>(null);
	let cpuMetric = $state<CpuMetric | null>(null);
	let ramMetric = $state<RamMetric | null>(null);
	let loading = $state(true);
	let error = $state<string>('');
	let tpsEventSource = $state<EventSource | null>(null);
	let sessionEventSource = $state<EventSource | null>(null);
	let nativeQueryEventSource = $state<EventSource | null>(null);
	let lockEventSource = $state<EventSource | null>(null);
	let serverMetricsEventSource = $state<EventSource | null>(null);

	// Lock tooltip
	let lockTooltip = $state<{ text: string; x: number; y: number } | null>(null);

	function getLockExplanation(mode: string): string {
		const explanations: Record<string, string> = {
			AccessShareLock:
				'Read lock — multiple transactions can hold it concurrently. Blocks schema changes.',
			RowShareLock:
				'Row share lock — acquired by SELECT FOR UPDATE/SHARE. Blocks exclusive table locks.',
			RowExclusiveLock:
				'Row exclusive lock — acquired by INSERT, UPDATE, DELETE. Blocks share locks and schema changes.',
			ShareUpdateExclusiveLock:
				'Lock taken by VACUUM, ANALYZE and CREATE INDEX CONCURRENTLY. Blocks other VACUUMs and schema changes.',
			ShareLock: 'Share lock — acquired by CREATE INDEX. Blocks write operations on the table.',
			ShareRowExclusiveLock:
				'Share row exclusive lock — blocks concurrent writes and other share locks.',
			ExclusiveLock: 'Exclusive lock — blocks reads and writes on the table.',
			AccessExclusiveLock:
				'Strongest lock — acquired by DROP, TRUNCATE, ALTER and VACUUM FULL. Blocks all other access.'
		};
		return explanations[mode] || `Lock mode ${mode}. See PostgreSQL documentation for details.`;
	}

	function showLockTooltip(event: MouseEvent, mode: string) {
		lockTooltip = { text: getLockExplanation(mode), x: event.clientX, y: event.clientY - 12 };
	}

	function moveLockTooltip(event: MouseEvent) {
		if (lockTooltip) {
			lockTooltip = { ...lockTooltip, x: event.clientX, y: event.clientY - 12 };
		}
	}

	function hideLockTooltip() {
		lockTooltip = null;
	}

	// Modal states
	let showServerModal = $state(false);
	let showDbModal = $state(false);
	let createdServerId = $state<string>('');
	let servers = $state<ServerListItem[]>([]);

	// Server form
	let srvName = $state('');
	let srvHost = $state('');
	let srvPort = $state('5432');
	let srvUser = $state('');
	let srvPass = $state('');
	let srvSsl = $state('prefer');
	let testResult = $state<{ ok: boolean; msg: string } | null>(null);
	let testing = $state(false);
	let creatingServer = $state(false);

	// Database form
	let dbServerId = $state('');
	let dbName = $state('');
	let creatingDb = $state(false);
	let dbError = $state('');

	function clearDatabaseContext() {
		selectedDb = null;
		stats = null;
		uptime = null;
		tps = 0;
		sessions = null;
		nativeQueries = null;
		locks = null;
		cpuMetric = null;
		ramMetric = null;

		if (tpsEventSource) {
			tpsEventSource.close();
			tpsEventSource = null;
		}
		if (sessionEventSource) {
			sessionEventSource.close();
			sessionEventSource = null;
		}
		if (nativeQueryEventSource) {
			nativeQueryEventSource.close();
			nativeQueryEventSource = null;
		}
		if (lockEventSource) {
			lockEventSource.close();
			lockEventSource = null;
		}
		if (serverMetricsEventSource) {
			serverMetricsEventSource.close();
			serverMetricsEventSource = null;
		}
	}

	async function loadDashboard() {
		try {
			loading = true;
			error = '';
			databases = await listDatabases();

			if (databases.length === 0) {
				clearDatabaseContext();
				return;
			}

			const routeDbId = $page.params.database_id;
			selectedDb = databases.find((db) => db.id === routeDbId) ?? databases[0];
			if (selectedDb.id !== routeDbId) {
				goto(`/overview/${selectedDb.id}`, { replaceState: true });
				return;
			}
			selectedDatabaseId.set(selectedDb.id);
			const dbId = selectedDb.id;

			const [statsData, uptimeData] = await Promise.all([
				getDatabaseStats(dbId),
				getDatabaseUptime(dbId)
			]);

			stats = statsData;
			uptime = uptimeData;
			connectStreams(selectedDb);
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			clearDatabaseContext();
			error = err.message || 'Failed to load dashboard data.';
		} finally {
			loading = false;
		}
	}

	function connectTpsStream(dbId: string) {
		if (tpsEventSource) tpsEventSource.close();
		tpsEventSource = createTpsEventSource(dbId);
		tpsEventSource.addEventListener('tps', (event) => {
			try {
				const data = JSON.parse((event as MessageEvent).data);
				if (data.tps !== undefined) tps = data.tps;
			} catch {
				/* ignore */
			}
		});
		tpsEventSource.onerror = () => {
			/* browser auto-reconnects */
		};
	}

	function connectStreams(db: DatabaseListItem) {
		connectTpsStream(db.id);
		connectSessionStream(db.id);
		connectNativeQueryStream(db.id);
		connectLockStream(db.id);
		connectServerMetricsStream(db.server_id);
	}

	function connectSessionStream(dbId: string) {
		sessions = null;
		if (sessionEventSource) sessionEventSource.close();
		sessionEventSource = createSessionEventSource(dbId);
		sessionEventSource.addEventListener('sessions', (event) => {
			sessions = JSON.parse((event as MessageEvent).data);
		});
		sessionEventSource.onerror = () => {
			/* browser auto-reconnects */
		};
	}

	function applyNativeQuerySnapshot(rows: NativeQueryMetric[]) {
		nativeQueries = rows
			.sort((a, b) => new Date(b.collected_at).getTime() - new Date(a.collected_at).getTime())
			.slice(0, 200);
	}

	function connectNativeQueryStream(dbId: string) {
		nativeQueries = null;
		if (nativeQueryEventSource) nativeQueryEventSource.close();
		nativeQueryEventSource = createNativeQueryEventSource(dbId);
		nativeQueryEventSource.addEventListener('native_query', (event) => {
			applyNativeQuerySnapshot(JSON.parse((event as MessageEvent).data));
		});
		nativeQueryEventSource.onerror = () => {
			/* browser auto-reconnects */
		};
	}

	function connectLockStream(dbId: string) {
		locks = null;
		if (lockEventSource) lockEventSource.close();
		lockEventSource = createLockEventSource(dbId);
		lockEventSource.addEventListener('locks', (event) => {
			locks = JSON.parse((event as MessageEvent).data);
		});
		lockEventSource.onerror = () => {
			/* browser auto-reconnects */
		};
	}

	function connectServerMetricsStream(serverId: string) {
		cpuMetric = null;
		ramMetric = null;
		if (serverMetricsEventSource) serverMetricsEventSource.close();
		serverMetricsEventSource = createServerMetricsEventSource(serverId);
		serverMetricsEventSource.addEventListener('cpu', (event) => {
			cpuMetric = JSON.parse((event as MessageEvent).data);
		});
		serverMetricsEventSource.addEventListener('ram', (event) => {
			ramMetric = JSON.parse((event as MessageEvent).data);
		});
		serverMetricsEventSource.onerror = () => {
			/* browser auto-reconnects */
		};
	}

	function formatMilliseconds(value: number | null): string {
		if (value === null || value === undefined) return '--';
		if (value < 1000) return `${Math.round(value)}ms`;
		const seconds = value / 1000;
		if (seconds < 60) return `${seconds.toFixed(1)}s`;
		const minutes = Math.floor(seconds / 60);
		return `${minutes}m ${Math.round(seconds % 60)}s`;
	}

	function dashboardQueries(): NativeQueryMetric[] {
		return [...(nativeQueries ?? [])]
			.filter((query) => query.state === 'active' && Boolean(query.query))
			.sort((a, b) => (b.query_duration_ms ?? 0) - (a.query_duration_ms ?? 0));
	}

	async function handleTestConnection() {
		testing = true;
		testResult = null;
		try {
			const res = await testConnection({
				name: srvName || 'Test',
				host: srvHost,
				port: srvPort,
				username: srvUser,
				password: srvPass,
				ssl_mode: srvSsl
			});
			if (res.status === 'success') {
				testResult = { ok: true, msg: `Connection successful. ${res.version} is reachable.` };
			} else {
				testResult = { ok: false, msg: `${res.code}. ${res.detail}` };
			}
		} catch (err: any) {
			testResult = { ok: false, msg: err.message || 'Could not run the connection test.' };
		} finally {
			testing = false;
		}
	}

	async function handleCreateServer() {
		creatingServer = true;
		try {
			const res: ServerCreatedResponse = await createServer({
				name: srvName,
				host: srvHost,
				port: srvPort,
				username: srvUser,
				password: srvPass,
				ssl_mode: srvSsl
			});
			createdServerId = res.id;
			showServerModal = false;
			showDbModal = true;
			resetServerForm();
			// pre-load servers for db modal
			servers = await listServers();
			dbServerId = createdServerId;
		} catch (err: any) {
			testResult = { ok: false, msg: err.message || 'Failed to create server' };
		} finally {
			creatingServer = false;
		}
	}

	async function handleCreateDatabase() {
		creatingDb = true;
		dbError = '';
		try {
			await createDatabase({
				server_id: dbServerId,
				db_name: dbName
			});
			showDbModal = false;
			resetDbForm();
			await loadDashboard();
		} catch (err: any) {
			dbError = err.message || 'Failed to create database';
		} finally {
			creatingDb = false;
		}
	}

	function resetServerForm() {
		srvName = '';
		srvHost = '';
		srvPort = '5432';
		srvUser = '';
		srvPass = '';
		srvSsl = 'prefer';
		testResult = null;
	}

	function resetDbForm() {
		dbServerId = '';
		dbName = '';
		dbError = '';
	}

	function openServerModal() {
		resetServerForm();
		showServerModal = true;
	}

	function closeServerModal() {
		showServerModal = false;
		resetServerForm();
	}

	function closeDbModal() {
		showDbModal = false;
		resetDbForm();
	}

	onMount(() => {
		loadDashboard();
	});

	onDestroy(() => {
		if (tpsEventSource) tpsEventSource.close();
		if (sessionEventSource) sessionEventSource.close();
		if (nativeQueryEventSource) nativeQueryEventSource.close();
		if (lockEventSource) lockEventSource.close();
		if (serverMetricsEventSource) serverMetricsEventSource.close();
	});
</script>

<!-- Server Modal -->
{#if showServerModal}
	<div class="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4">
		<div class="glass-panel w-full max-w-lg p-8 shadow-floating">
			<div class="flex items-center justify-between mb-6">
				<div class="flex items-center gap-3">
					<div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
						<span class="material-symbols-outlined text-primary">dns</span>
					</div>
					<div>
						<h2 class="font-headline-md text-headline-md font-bold text-on-surface m-0">
							New Server
						</h2>
						<p class="text-[11px] text-on-surface-variant mt-0.5">
							Configure PostgreSQL connection
						</p>
					</div>
				</div>
				<button
					onclick={closeServerModal}
					class="text-on-surface-variant hover:text-error transition-colors"
				>
					<span class="material-symbols-outlined text-[20px]">close</span>
				</button>
			</div>

			<div class="space-y-4">
				<div>
					<label
						class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
						for="srvName">Server Name</label
					>
					<div class="relative group mt-1.5">
						<span
							class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant group-focus-within:text-primary transition-colors text-[18px]"
							>badge</span
						>
						<input
							bind:value={srvName}
							class="input-technical text-code-md pl-10 pr-4 py-2.5 w-full"
							id="srvName"
							placeholder="Production-01"
						/>
					</div>
				</div>

				<div class="grid grid-cols-3 gap-3">
					<div class="col-span-2">
						<label
							class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
							for="srvHost">Host</label
						>
						<div class="relative group mt-1.5">
							<span
								class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant group-focus-within:text-primary transition-colors text-[18px]"
								>link</span
							>
							<input
								bind:value={srvHost}
								class="input-technical text-code-md pl-10 pr-4 py-2.5 w-full"
								id="srvHost"
								placeholder="db.example.com"
							/>
						</div>
					</div>
					<div>
						<label
							class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
							for="srvPort">Port</label
						>
						<input
							bind:value={srvPort}
							class="input-technical text-code-md px-4 py-2.5 w-full mt-1.5"
							id="srvPort"
							placeholder="5432"
						/>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-3">
					<div>
						<label
							class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
							for="srvUser">Username</label
						>
						<div class="relative group mt-1.5">
							<span
								class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant group-focus-within:text-primary transition-colors text-[18px]"
								>person</span
							>
							<input
								bind:value={srvUser}
								class="input-technical text-code-md pl-10 pr-4 py-2.5 w-full"
								id="srvUser"
								placeholder="postgres"
							/>
						</div>
					</div>
					<div>
						<label
							class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
							for="srvPass">Password</label
						>
						<div class="relative group mt-1.5">
							<span
								class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant group-focus-within:text-primary transition-colors text-[18px]"
								>lock</span
							>
							<input
								bind:value={srvPass}
								type="password"
								class="input-technical text-code-md pl-10 pr-4 py-2.5 w-full"
								id="srvPass"
								placeholder="••••••••"
							/>
						</div>
					</div>
				</div>

				<div>
					<label
						class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
						for="srvSsl">SSL Mode</label
					>
					<select
						bind:value={srvSsl}
						class="input-technical text-code-md px-4 py-2.5 w-full mt-1.5"
						id="srvSsl"
					>
						<option value="prefer">prefer</option>
						<option value="require">require</option>
						<option value="disable">disable</option>
						<option value="verify-ca">verify-ca</option>
						<option value="verify-full">verify-full</option>
					</select>
				</div>

				{#if testResult}
					<div
						class="bg-{testResult.ok
							? 'primary'
							: 'error'}-container/20 border-l-4 border-{testResult.ok
							? 'primary'
							: 'error'} p-3 rounded-r flex items-start gap-2"
					>
						<span
							class="material-symbols-outlined text-{testResult.ok
								? 'primary'
								: 'error'} text-[18px]">{testResult.ok ? 'check_circle' : 'error'}</span
						>
						<p class="font-code-sm text-xs text-{testResult.ok ? 'primary' : 'error'} mt-0.5">
							{testResult.msg}
						</p>
					</div>
				{/if}

				<div class="flex gap-3 pt-2">
					<button
						onclick={handleTestConnection}
						disabled={testing || !srvHost || !srvUser || !srvPass}
						class="btn-secondary flex-1 py-2.5 font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
					>
						{#if testing}
							<svg
								class="animate-spin h-4 w-4"
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
							<span>Testing...</span>
						{:else}
							<span class="material-symbols-outlined text-sm">network_check</span>
							<span>Test Connection</span>
						{/if}
					</button>
					<button
						onclick={handleCreateServer}
						disabled={creatingServer || !srvName || !srvHost || !srvUser || !srvPass}
						class="btn-primary flex-1 py-2.5 font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
					>
						{#if creatingServer}
							<svg
								class="animate-spin h-4 w-4"
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
							<span>Creating...</span>
						{:else}
							<span class="material-symbols-outlined text-sm">arrow_forward</span>
							<span>Continue</span>
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- Database Modal -->
{#if showDbModal}
	<div class="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4">
		<div class="glass-panel w-full max-w-md p-8 shadow-floating">
			<div class="flex items-center justify-between mb-6">
				<div class="flex items-center gap-3">
					<div class="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
						<span class="material-symbols-outlined text-primary">database</span>
					</div>
					<div>
						<h2 class="font-headline-md text-headline-md font-bold text-on-surface m-0">
							Link Database
						</h2>
						<p class="text-[11px] text-on-surface-variant mt-0.5">
							Select a server and database name
						</p>
					</div>
				</div>
				<button
					onclick={closeDbModal}
					class="text-on-surface-variant hover:text-error transition-colors"
				>
					<span class="material-symbols-outlined text-[20px]">close</span>
				</button>
			</div>

			<div class="space-y-4">
				<div>
					<label
						class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
						for="dbServer">Server</label
					>
					<select
						bind:value={dbServerId}
						class="input-technical text-code-md px-4 py-2.5 w-full mt-1.5"
						id="dbServer"
					>
						<option value="">Select a server...</option>
						{#each servers as s}
							<option value={s.id}>{s.name}</option>
						{/each}
					</select>
				</div>

				<div>
					<label
						class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
						for="dbName">Database Name</label
					>
					<div class="relative group mt-1.5">
						<span
							class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant group-focus-within:text-primary transition-colors text-[18px]"
							>storage</span
						>
						<input
							bind:value={dbName}
							class="input-technical text-code-md pl-10 pr-4 py-2.5 w-full"
							id="dbName"
							placeholder="postgres"
						/>
					</div>
				</div>

				{#if dbError}
					<div
						class="bg-error-container/20 border-l-4 border-error p-3 rounded-r flex items-start gap-2"
					>
						<span class="material-symbols-outlined text-error text-[18px]">error</span>
						<p class="font-code-sm text-xs text-error mt-0.5">{dbError}</p>
					</div>
				{/if}

				<div class="flex gap-3 pt-2">
					<button
						onclick={closeDbModal}
						class="btn-secondary flex-1 py-2.5 font-bold text-sm cursor-pointer"
					>
						Cancel
					</button>
					<button
						onclick={handleCreateDatabase}
						disabled={creatingDb || !dbServerId || !dbName}
						class="btn-primary flex-1 py-2.5 font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
					>
						{#if creatingDb}
							<svg
								class="animate-spin h-4 w-4"
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
							<span>Creating...</span>
						{:else}
							<span class="material-symbols-outlined text-sm">add_link</span>
							<span>Link Database</span>
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- TopAppBar -->
<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-4">
		<span class="material-symbols-outlined text-primary">dns</span>
		<div class="flex items-center gap-3">
			<h1 class="font-headline-md text-headline-md text-on-background m-0">
				{#if selectedDb}
					Database: {selectedDb.name}
				{:else}
					Database Cluster
				{/if}
			</h1>
			{#if selectedDb}
				<span
					class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-primary/10 text-primary border border-primary/20"
				>
					<span class="w-1.5 h-1.5 rounded-full bg-primary mr-1.5 status-pulse"></span>
					HEALTHY
				</span>
			{/if}
		</div>
	</div>
	<div class="flex items-center gap-6">
		{#if databases.length > 0 && uptime}
			<div
				class="hidden lg:flex items-center gap-2 px-3 py-1 bg-surface-container rounded-lg border border-outline-variant"
			>
				<span class="text-[10px] font-label-caps text-on-surface-variant">UPTIME</span>
				<span class="font-code-sm text-primary">{uptime.uptime_formatted}</span>
			</div>
		{/if}
		{#if databases.length > 0}
			<button
				onclick={loadDashboard}
				class="flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-lg font-bold text-sm duration-200 ease-in-out hover:brightness-110 active:scale-95 cursor-pointer"
			>
				<span class="material-symbols-outlined text-sm">sync</span>
				Live Sync
			</button>
		{/if}
	</div>
</header>

<!-- Canvas -->
<div class="pt-24 px-container-padding pb-12">
	{#if loading}
		<div class="flex items-center justify-center py-12">
			<svg
				class="animate-spin h-8 w-8 text-primary"
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
		<!-- Empty State -->
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
				You haven't linked any PostgreSQL databases yet. Connect a server and link a database to
				start monitoring.
			</p>
			<button
				onclick={openServerModal}
				class="btn-primary px-8 py-3 font-bold text-sm flex items-center gap-2 cursor-pointer"
			>
				<span class="material-symbols-outlined text-sm">add_link</span>
				Connect Database
			</button>
		</div>
	{:else}
		{#if databases.length > 0 && error}
			<div class="mb-4 p-4 bg-error-container/20 border-l-4 border-error rounded-r">
				<p class="font-code-sm text-sm text-error">{error}</p>
			</div>
		{/if}

		<!-- KPI Grid -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-panel-gap mb-panel-gap">
			<!-- Active Connections -->
			<div
				class="bg-surface-container border border-outline-variant p-4 flex flex-col gap-1 rounded-lg"
			>
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>ACTIVE CONNECTIONS</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-primary font-mono"
						>{sessions ? sessions.length : '--'}</span
					>
					<span class="text-on-surface-variant text-[10px]">
						{#if sessions}
							{sessions.filter((session) => session.state === 'active').length} active
						{:else}
							--
						{/if}
					</span>
				</div>
				<div class="w-full h-1 bg-surface-variant mt-2 rounded-full overflow-hidden">
					<div
						class="h-full bg-primary rounded-full"
						style="width: {sessions ? Math.min(sessions.length * 5, 100) : 0}%"
					></div>
				</div>
			</div>

			<!-- CPU Usage -->
			<div
				class="bg-surface-container border border-outline-variant p-4 flex flex-col gap-1 rounded-lg"
			>
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>CPU USAGE</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-on-surface font-mono"
						>{cpuMetric?.cpu_percent != null ? `${cpuMetric.cpu_percent.toFixed(1)}%` : '--'}</span
					>
					<span class="text-on-surface-variant text-[10px]"
						>{cpuMetric?.cpu_count ? `${cpuMetric.cpu_count} cores` : '--'}</span
					>
				</div>
				<div class="w-full h-1 bg-surface-variant mt-2 rounded-full overflow-hidden">
					<div
						class="h-full bg-primary-container rounded-full"
						style="width: {cpuMetric?.cpu_percent ?? 0}%"
					></div>
				</div>
			</div>

			<!-- Memory -->
			<div
				class="bg-surface-container border border-outline-variant p-4 flex flex-col gap-1 rounded-lg"
			>
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>MEMORY</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-on-surface font-mono"
						>{ramMetric?.used_bytes != null ? formatBytes(ramMetric.used_bytes) : '--'}</span
					>
					<span class="text-on-surface-variant text-[10px]"
						>{ramMetric?.total_bytes != null
							? `of ${formatBytes(ramMetric.total_bytes)}`
							: '--'}</span
					>
				</div>
				<div class="w-full h-1 bg-surface-variant mt-2 rounded-full overflow-hidden">
					<div
						class="h-full bg-primary-container rounded-full"
						style="width: {ramMetric?.percent ?? 0}%"
					></div>
				</div>
			</div>

			<!-- Transactions/sec -->
			<div
				class="bg-surface-container border border-outline-variant p-4 flex flex-col gap-1 rounded-lg"
			>
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>TRANSACTIONS/SEC</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-tertiary font-mono"
						>{tps.toLocaleString()}</span
					>
					<span class="text-tertiary text-[10px] font-bold">↑ Peak</span>
				</div>
				<div class="w-full h-1 bg-surface-variant mt-2 rounded-full overflow-hidden">
					<div
						class="h-full bg-tertiary-container rounded-full"
						style="width: {Math.min((tps / 3000) * 100, 100)}%"
					></div>
				</div>
			</div>
		</div>

		<!-- Bento Layout Content -->
		<div class="grid grid-cols-12 gap-panel-gap">
			<!-- Active Queries (Left Col) -->
			<div
				class="col-span-12 lg:col-span-8 bg-surface-container border border-outline-variant rounded-lg flex flex-col overflow-hidden h-[480px]"
			>
				<div
					class="px-4 py-3 border-b border-outline-variant flex justify-between items-center bg-surface-container-low"
				>
					<div class="flex items-center gap-2">
						<span class="material-symbols-outlined text-primary text-sm">terminal</span>
						<h2 class="font-headline-md text-headline-md m-0">Active queries</h2>
					</div>
					<button class="text-[10px] font-label-caps text-primary hover:underline cursor-pointer"
						>VIEW ALL</button
					>
				</div>
				<div class="flex-1 overflow-auto custom-scrollbar">
					<table class="w-full table-fixed text-left border-collapse">
						<colgroup>
							<col class="w-24" />
							<col class="w-28" />
							<col />
							<col class="w-20" />
						</colgroup>
						<thead class="sticky top-0 z-10">
							<tr class="bg-surface-container-high">
								<th
									class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant"
									>PID</th
								>
								<th
									class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant"
									>DURATION</th
								>
								<th
									class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant"
									>SQL SNIPPET</th
								>
								<th
									class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] border-b border-outline-variant text-center"
									>WAIT</th
								>
							</tr>
						</thead>
						<tbody class="divide-y divide-outline-variant/30">
							{#if nativeQueries === null}
								<tr class="h-[72px]">
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant truncate"
										>--</td
									>
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant truncate"
										>--</td
									>
									<td class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant truncate"
										>Waiting for native query samples</td
									>
									<td class="px-4 py-3 text-center"
										><span class="material-symbols-outlined text-on-surface-variant text-[16px]"
											>hourglass_empty</span
										></td
									>
								</tr>
							{:else if dashboardQueries().length === 0}
								<tr>
									<td colspan="4" class="px-4 py-20 text-center text-on-surface-variant text-sm"
										>No active queries in the latest collector samples</td
									>
								</tr>
							{:else}
								{#each dashboardQueries() as query}
									<tr class="h-[72px] hover:bg-surface-variant/20 transition-colors">
										<td
											class="px-4 py-3 font-code-sm text-code-sm text-on-surface-variant truncate"
											title={String(query.pid)}>{query.pid}</td
										>
										<td
											class="px-4 py-3 font-code-sm text-code-sm truncate {query.state === 'active'
												? 'text-tertiary font-bold'
												: 'text-on-surface'}">{formatMilliseconds(query.query_duration_ms)}</td
										>
										<td class="px-4 py-3 min-w-0">
											<div class="flex items-center gap-2 mb-1">
												<span
													class="text-[10px] text-on-surface-variant font-label-caps truncate max-w-32"
													>{query.user_name || '--'}</span
												>
												<span
													class="text-[10px] px-1.5 py-0.5 rounded border border-outline-variant text-on-surface-variant shrink-0"
													>{query.state || '--'}</span
												>
											</div>
											<code
												class="font-code-sm text-code-sm text-on-surface block w-full truncate"
												title={query.query || '--'}>{query.query || '--'}</code
											>
										</td>
										<td class="px-4 py-3 text-center">
											<span
												class="material-symbols-outlined {query.wait_event
													? 'text-error'
													: 'text-primary'} text-[16px]"
												title={query.wait_event || 'No wait event'}
												>{query.wait_event ? 'close' : 'check'}</span
											>
										</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			</div>

			<!-- Live Locks & Stats (Right Col) -->
			<div class="col-span-12 lg:col-span-4 h-[480px] grid grid-rows-2 gap-panel-gap">
				<!-- Live Locks -->
				<div
					class="bg-surface-container border border-outline-variant flex flex-col rounded-lg overflow-hidden"
				>
					<div
						class="px-4 py-3 border-b border-outline-variant flex items-center gap-2 bg-surface-container-low"
					>
						<span class="material-symbols-outlined text-error text-sm">lock</span>
						<h2 class="font-headline-md text-headline-md m-0">Live Locks</h2>
					</div>
					<div class="p-2 space-y-2 flex-1 overflow-y-auto custom-scrollbar bg-surface-container">
						{#if locks === null}
							<div
								class="p-3 bg-surface-container-high border-l-4 border-outline flex justify-between items-center rounded-r"
							>
								<div>
									<p class="text-[11px] font-bold text-on-surface-variant uppercase">--</p>
									<p class="text-xs font-code-sm mt-1 text-on-surface-variant">
										Waiting for collector data
									</p>
								</div>
								<span class="material-symbols-outlined text-on-surface-variant text-[20px]"
									>hourglass_empty</span
								>
							</div>
						{:else if locks.length === 0}
							<div
								class="p-3 bg-surface-container-high border-l-4 border-primary flex justify-between items-center rounded-r"
							>
								<div>
									<p class="text-[11px] font-bold text-primary uppercase">No active locks</p>
									<p class="text-xs font-code-sm mt-1 text-on-surface-variant">
										Latest collector sample is clear
									</p>
								</div>
								<span class="material-symbols-outlined text-primary text-[20px]">check_circle</span>
							</div>
						{:else}
							{#each locks as lock}
								<div
									class="{lock.is_granted === false
										? 'bg-error-container/10 border-error'
										: 'bg-surface-container-high border-outline'} p-3 border-l-4 flex justify-between items-center rounded-r"
								>
									<div class="min-w-0">
										<p
											class="{lock.is_granted === false
												? 'text-error'
												: 'text-on-surface-variant'} text-[11px] font-bold uppercase"
										>
											{lock.mode}
										</p>
										<p class="text-xs font-code-sm mt-1 text-on-surface-variant">
											PID: {lock.holder_pid} -> table #{lock.table_id}
										</p>
										{#if lock.query_preview}
											<p class="text-xs font-code-sm mt-1 text-on-surface truncate max-w-[260px]">
												{lock.query_preview}
											</p>
										{/if}
									</div>
									<button
										type="button"
										class="{lock.is_granted === false
											? 'text-error'
											: 'text-on-surface-variant'} material-symbols-outlined text-[20px] cursor-help"
										onmouseenter={(event) => showLockTooltip(event, lock.mode)}
										onmousemove={moveLockTooltip}
										onmouseleave={hideLockTooltip}
										aria-label="Lock explanation"
									>
										{lock.is_granted === false ? 'warning' : 'help'}
									</button>
								</div>
							{/each}
						{/if}
					</div>
					<div class="p-3 bg-surface-container-low text-center border-t border-outline-variant">
						<p class="text-[10px] text-on-surface-variant font-label-caps">
							{#if locks === null}
								-- locks detected
							{:else}
								{locks.filter((lock) => lock.is_granted === false).length} waiting locks detected
							{/if}
						</p>
					</div>
				</div>
				<!-- Schema overview -->
				<div
					class="bg-surface-container border border-outline-variant flex flex-col rounded-lg overflow-hidden"
				>
					<div
						class="px-4 py-3 border-b border-outline-variant flex items-center gap-2 bg-surface-container-low"
					>
						<span class="material-symbols-outlined text-primary-container text-sm">grid_view</span>
						<h2 class="font-headline-md text-headline-md m-0">Schema overview</h2>
					</div>
					<div class="p-4 grid grid-cols-2 gap-4">
						<div
							class="bg-surface-container-high p-3 rounded-lg text-center border border-outline-variant/30"
						>
							<p class="text-[10px] font-label-caps text-on-surface-variant mb-1">TABLES</p>
							<p class="text-xl font-bold font-metric-lg text-on-surface">
								{#if stats}{stats.table_count}{:else}--{/if}
							</p>
						</div>
						<div
							class="bg-surface-container-high p-3 rounded-lg text-center border border-outline-variant/30"
						>
							<p class="text-[10px] font-label-caps text-on-surface-variant mb-1">INDICES</p>
							<p class="text-xl font-bold font-metric-lg text-on-surface">
								{#if stats}{stats.index_count}{:else}--{/if}
							</p>
						</div>
						<div
							class="bg-surface-container-high p-3 rounded-lg text-center border border-outline-variant/30"
						>
							<p class="text-[10px] font-label-caps text-on-surface-variant mb-1">VIEWS</p>
							<p class="text-xl font-bold font-metric-lg text-on-surface">
								{#if stats}{stats.view_count}{:else}--{/if}
							</p>
						</div>
						<div
							class="bg-surface-container-high p-3 rounded-lg text-center border border-outline-variant/30"
						>
							<p class="text-[10px] font-label-caps text-on-surface-variant mb-1">SIZE</p>
							<p class="text-xl font-bold font-metric-lg text-on-surface">
								{#if stats}{formatBytes(stats.size_bytes)}{:else}--{/if}
							</p>
						</div>
					</div>
					<div class="px-4 pb-4">
						<div class="flex justify-between items-center mb-2">
							<span class="text-[10px] font-label-caps text-on-surface-variant">INDEX HIT RATE</span
							>
							<span class="text-[10px] font-bold text-primary">
								{#if stats && stats.index_hit_rate !== null}{stats.index_hit_rate}%{:else}--{/if}
							</span>
						</div>
						<div class="w-full h-1.5 bg-surface-variant rounded-full overflow-hidden">
							<div
								class="h-full bg-primary rounded-full"
								style="width: {stats?.index_hit_rate ?? 0}%"
							></div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<!-- Footer / Log Stream Area -->
		<div
			class="mt-panel-gap bg-surface-container-lowest border border-outline-variant font-code-sm text-code-sm p-4 overflow-hidden rounded-lg"
		>
			<div class="flex justify-between items-center mb-3">
				<span
					class="font-label-caps text-on-surface-variant flex items-center gap-2 tracking-widest"
				>
					<span class="w-2 h-2 rounded-full bg-primary status-pulse"></span>
					LIVE POSTGRES LOGS
				</span>
				<span class="text-on-surface-variant opacity-50 text-[10px] font-label-caps"
					>Stream: Active</span
				>
			</div>
			<div class="space-y-1 opacity-80 text-on-surface">
				<p>
					<span class="text-on-surface-variant">[2023-10-27 14:32:01]</span>
					<span class="text-primary-container font-bold">LOG:</span> checkpoint starting: time
				</p>
				<p>
					<span class="text-on-surface-variant">[2023-10-27 14:32:04]</span>
					<span class="text-primary-container font-bold">LOG:</span> checkpoint complete: wrote 428 buffers
					(0.1%)
				</p>
				<p>
					<span class="text-on-surface-variant">[2023-10-27 14:32:15]</span>
					<span class="text-tertiary font-bold">WARNING:</span> autovacuum worker took too long on "public.audit_log"
				</p>
				<p>
					<span class="text-on-surface-variant">[2023-10-27 14:32:45]</span>
					<span class="text-primary-container font-bold">LOG:</span> disconnection: session time: 0:00:12.454
					user=admin_root
				</p>
			</div>
		</div>
	{/if}
</div>

{#if lockTooltip}
	<div
		class="fixed z-50 max-w-xs rounded-lg border border-outline-variant bg-inverse-surface px-3 py-2 text-xs text-inverse-on-surface shadow-lg pointer-events-none"
		style={'left: ' +
			lockTooltip.x +
			'px; top: ' +
			lockTooltip.y +
			'px; transform: translate(-50%, -100%);'}
	>
		{lockTooltip.text}
	</div>
{/if}

<!-- Floating Action Button (FAB) - Global Command -->
<button
	class="fixed bottom-6 right-6 w-14 h-14 bg-primary text-on-primary rounded-full shadow-floating flex items-center justify-center hover:scale-105 active:scale-95 transition-transform group z-50 cursor-pointer"
>
	<span class="material-symbols-outlined text-[28px] group-hover:rotate-90 transition-transform"
		>add</span
	>
</button>

<style>
	.glass-panel {
		background-color: rgba(26, 33, 31, 0.95);
		backdrop-filter: blur(12px);
		-webkit-backdrop-filter: blur(12px);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 16px;
	}
	.input-technical {
		background-color: rgba(14, 21, 19, 0.8);
		border: 1px solid rgba(133, 148, 144, 0.2);
		color: var(--color-on-surface);
		font-family: 'JetBrains Mono', monospace;
		border-radius: 8px;
		transition: all 0.3s ease;
	}
	.input-technical:focus {
		border-color: var(--color-primary);
		background-color: var(--color-surface-container-low);
		outline: none;
		box-shadow: 0 0 0 3px rgba(79, 219, 200, 0.15);
	}
	.btn-primary {
		background: linear-gradient(
			135deg,
			var(--color-primary) 0%,
			var(--color-primary-container) 100%
		);
		color: var(--color-on-primary-container);
		border-radius: 8px;
		transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
		box-shadow: 0 4px 14px 0 rgba(20, 184, 166, 0.39);
	}
	.btn-primary:hover:not(:disabled) {
		transform: translateY(-2px);
		box-shadow: 0 6px 20px rgba(20, 184, 166, 0.5);
	}
	.btn-primary:active:not(:disabled) {
		transform: translateY(0);
		box-shadow: 0 2px 8px rgba(20, 184, 166, 0.3);
	}
	.btn-secondary {
		background: rgba(60, 73, 71, 0.6);
		color: var(--color-on-surface);
		border: 1px solid rgba(133, 148, 144, 0.2);
		border-radius: 8px;
		transition: all 0.3s ease;
	}
	.btn-secondary:hover:not(:disabled) {
		background: rgba(60, 73, 71, 0.8);
		border-color: rgba(133, 148, 144, 0.4);
	}
	.modal-overlay {
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(4px);
	}
</style>
