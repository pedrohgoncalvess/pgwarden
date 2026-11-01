<script lang="ts">
	import Select from '$lib/components/Select.svelte';
	import { onMount, onDestroy } from 'svelte';
	import { fly } from 'svelte/transition';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import {
		listDatabases,
		getDatabaseMetricsSummary,
		createTpsEventSource,
		formatBytes,
		listServers,
		testConnection,
		createServer,
		createDatabase,
		createSessionEventSource,
		createLockEventSource,
		createServerMetricsEventSource,
		createNativeQueryEventSource,
		getServiceHealth
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
		NativeQueryMetric,
		HealthResponse
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
	let serviceHealth = $state<HealthResponse | null>(null);
	let quickActionsOpen = $state(false);
	let lastUpdated = $state<Date | null>(null);
	let failedStreams = $state<string[]>([]);
	let unavailableStreams = $state<string[]>([]);
	let connectedStreams = $state<string[]>([]);
	const streamError = $derived(failedStreams.length > 0);
	const streamWarning = $derived(streamError || unavailableStreams.length > 0);
	let paused = $state(false);
	let disposed = false;
	let loadSequence = 0;
	let loadController: AbortController | null = null;
	const activeSessionCount = $derived(
		sessions?.filter((session) => session.state === 'active').length ?? 0
	);
	const waitingLockCount = $derived(locks?.filter((lock) => lock.is_granted === false).length ?? 0);
	const activeQueries = $derived(
		[...(nativeQueries ?? [])]
			.filter((query) => query.state === 'active' && Boolean(query.query))
			.sort((a, b) => (b.query_duration_ms ?? 0) - (a.query_duration_ms ?? 0))
	);

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

	let showServerModal = $state(false);
	let showDbModal = $state(false);
	let overviewHelpOpen = $state(false);
	let createdServerId = $state<string>('');
	let servers = $state<ServerListItem[]>([]);
	const serverName = $derived(
		selectedDb ? (servers.find((s) => s.id === selectedDb!.server_id)?.name ?? '') : ''
	);

	let srvName = $state('');
	let srvHost = $state('');
	let srvPort = $state('5432');
	let srvUser = $state('');
	let srvPass = $state('');
	let srvSsl = $state('prefer');
	let testResult = $state<{ ok: boolean; msg: string } | null>(null);
	let testing = $state(false);
	let creatingServer = $state(false);

	let dbServerId = $state('');
	let dbName = $state('');
	let creatingDb = $state(false);
	let dbError = $state('');

	function clearDatabaseContext() {
		closeStreams();
		lastUpdated = null;
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
		const sequence = ++loadSequence;
		loadController?.abort();
		const controller = new AbortController();
		loadController = controller;
		try {
			loading = !selectedDb;
			error = '';
			const catalog = await Promise.all([listDatabases(), listServers()]);
			if (disposed || sequence !== loadSequence) return;
			[databases, servers] = catalog;

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

			const [metricsSummary, health] = await Promise.all([
				getDatabaseMetricsSummary(dbId, controller.signal),
				getServiceHealth().catch(() => null)
			]);
			if (disposed || sequence !== loadSequence) return;
			stats = metricsSummary.stats;
			uptime = metricsSummary.uptime;
			serviceHealth = health;
			if (document.visibilityState === 'visible') connectStreams(selectedDb);
		} catch (err: any) {
			if (disposed || sequence !== loadSequence) return;
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			if (!stats) clearDatabaseContext();
			error = err.message || 'Failed to load dashboard data.';
		} finally {
			if (!disposed && sequence === loadSequence) loading = false;
		}
	}

	function trackStream(source: EventSource, name: string, events: string[]) {
		const connected = () => {
			failedStreams = failedStreams.filter((item) => item !== name);
			connectedStreams = [...new Set([...connectedStreams, name])];
		};
		source.onopen = connected;
		source.onerror = (event) => {
			// Named API errors report collection failures, not transport disconnects.
			if (event instanceof MessageEvent) {
				unavailableStreams = [...new Set([...unavailableStreams, name])];
			} else {
				connectedStreams = connectedStreams.filter((item) => item !== name);
				failedStreams = [...new Set([...failedStreams, name])];
			}
		};
		for (const event of events) {
			source.addEventListener(event, () => {
				connected();
				unavailableStreams = unavailableStreams.filter((item) => item !== name);
				lastUpdated = new Date();
			});
		}
	}

	function connectTpsStream(dbId: string) {
		if (tpsEventSource) tpsEventSource.close();
		tpsEventSource = createTpsEventSource(dbId);
		tpsEventSource.addEventListener('tps', (event) => {
			try {
				const data = JSON.parse((event as MessageEvent).data);
				if (data.tps !== undefined) tps = data.tps;
			} catch {}
		});
		trackStream(tpsEventSource, 'tps', ['tps']);
	}

	function connectStreams(db: DatabaseListItem) {
		closeStreams();
		connectTpsStream(db.id);
		connectSessionStream(db.id);
		connectNativeQueryStream(db.id);
		connectLockStream(db.id);
		connectServerMetricsStream(db.server_id);
	}

	function connectSessionStream(dbId: string) {
		if (sessionEventSource) sessionEventSource.close();
		sessionEventSource = createSessionEventSource(dbId);
		sessionEventSource.addEventListener('sessions', (event) => {
			sessions = JSON.parse((event as MessageEvent).data);
		});
		trackStream(sessionEventSource, 'session', ['sessions']);
	}

	function applyNativeQuerySnapshot(rows: NativeQueryMetric[]) {
		nativeQueries = rows
			.sort((a, b) => new Date(b.collected_at).getTime() - new Date(a.collected_at).getTime())
			.slice(0, 200);
	}

	function connectNativeQueryStream(dbId: string) {
		if (nativeQueryEventSource) nativeQueryEventSource.close();
		nativeQueryEventSource = createNativeQueryEventSource(dbId);
		nativeQueryEventSource.addEventListener('native_query', (event) => {
			applyNativeQuerySnapshot(JSON.parse((event as MessageEvent).data));
		});
		trackStream(nativeQueryEventSource, 'nativeQuery', ['native_query']);
	}

	function connectLockStream(dbId: string) {
		if (lockEventSource) lockEventSource.close();
		lockEventSource = createLockEventSource(dbId);
		lockEventSource.addEventListener('locks', (event) => {
			locks = JSON.parse((event as MessageEvent).data);
		});
		trackStream(lockEventSource, 'lock', ['locks']);
	}

	function connectServerMetricsStream(serverId: string) {
		if (serverMetricsEventSource) serverMetricsEventSource.close();
		serverMetricsEventSource = createServerMetricsEventSource(serverId);
		serverMetricsEventSource.addEventListener('cpu', (event) => {
			cpuMetric = JSON.parse((event as MessageEvent).data);
		});
		serverMetricsEventSource.addEventListener('ram', (event) => {
			ramMetric = JSON.parse((event as MessageEvent).data);
		});
		trackStream(serverMetricsEventSource, 'serverMetrics', ['cpu', 'ram', 'disk', 'io']);
	}

	function formatMilliseconds(value: number | null): string {
		if (value === null || value === undefined) return '--';
		if (value < 1000) return `${Math.round(value)}ms`;
		const seconds = value / 1000;
		if (seconds < 60) return `${seconds.toFixed(1)}s`;
		const minutes = Math.floor(seconds / 60);
		return `${minutes}m ${Math.round(seconds % 60)}s`;
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

	function runQuickAction(action: 'alert' | 'metrics' | 'docs' | 'link') {
		quickActionsOpen = false;
		if (action === 'alert') goto('/alerts/configuration');
		if (action === 'metrics' && selectedDb) goto(`/analytics/${selectedDb.id}/data`);
		if (action === 'docs' && selectedDb) goto(`/schema/${selectedDb.id}/documentation`);
		if (action === 'link') {
			if (servers.length === 0) {
				openServerModal();
			} else {
				dbServerId = selectedDb?.server_id ?? servers[0].id;
				dbName = '';
				dbError = '';
				showDbModal = true;
			}
		}
	}

	function closeServerModal() {
		showServerModal = false;
		resetServerForm();
	}

	function closeDbModal() {
		showDbModal = false;
		resetDbForm();
	}

	function closeStreams() {
		failedStreams = [];
		unavailableStreams = [];
		connectedStreams = [];
		for (const source of [
			tpsEventSource,
			sessionEventSource,
			nativeQueryEventSource,
			lockEventSource,
			serverMetricsEventSource
		])
			source?.close();
	}
	onMount(() => {
		void loadDashboard();
		const visibility = () => {
			paused = document.visibilityState !== 'visible';
			if (paused) closeStreams();
			else if (selectedDb) connectStreams(selectedDb);
		};
		document.addEventListener('visibilitychange', visibility);
		return () => {
			disposed = true;
			loadSequence++;
			loadController?.abort();
			document.removeEventListener('visibilitychange', visibility);
			closeStreams();
		};
	});

	onDestroy(() => {
		if (tpsEventSource) tpsEventSource.close();
		if (sessionEventSource) sessionEventSource.close();
		if (nativeQueryEventSource) nativeQueryEventSource.close();
		if (lockEventSource) lockEventSource.close();
		if (serverMetricsEventSource) serverMetricsEventSource.close();
	});
</script>

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
						for="srvName">Server name</label
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
					<Select
						bind:value={srvSsl}
						class="w-full mt-1.5"
						id="srvSsl"
						aria-label="SSL mode"
						options={['prefer', 'require', 'disable', 'verify-ca', 'verify-full'].map((value) => ({
							value,
							label: value
						}))}
					/>
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
							<span>Test connection</span>
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
							Link database
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
					<Select
						bind:value={dbServerId}
						class="w-full mt-1.5"
						id="dbServer"
						aria-label="Server"
						options={[
							{ value: '', label: 'Select a server…' },
							...servers.map((item) => ({ value: item.id, label: item.name }))
						]}
					/>
				</div>

				<div>
					<label
						class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
						for="dbName">Database name</label
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
							<span>Link database</span>
						{/if}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

<header
	class="fixed top-0 right-0 app-page-header z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-4">
		<span class="material-symbols-outlined text-primary">dns</span>
		<div class="flex items-center gap-3">
			<h1 class="font-headline-md text-headline-md text-on-background m-0">
				{#if selectedDb}
					Database overview
				{:else}
					Database Cluster
				{/if}
			</h1>
			<div class="relative">
				<button
					onclick={() => (overviewHelpOpen = !overviewHelpOpen)}
					onmouseenter={() => (overviewHelpOpen = true)}
					onmouseleave={() => (overviewHelpOpen = false)}
					class="flex h-6 w-6 cursor-pointer items-center justify-center rounded-full border border-outline-variant text-on-surface-variant transition-colors hover:border-primary/40 hover:text-primary"
					aria-label="Overview page explanation"
				>
					<span class="material-symbols-outlined text-[14px]">help</span>
				</button>
				{#if overviewHelpOpen}
					<div
						class="absolute left-0 top-full z-50 mt-2 w-80 rounded-lg border border-outline-variant bg-surface-container-high p-3 text-xs text-on-surface shadow-lg"
					>
						<p class="mb-1 font-bold">What is this page?</p>
						<p class="mb-2 text-on-surface-variant">
							The Overview dashboard provides real-time monitoring of your PostgreSQL cluster. It
							displays key performance indicators like TPS (Transactions Per Second), active
							sessions, locking activity, and active queries.
						</p>
						<p class="font-bold">Tips</p>
						<p class="text-on-surface-variant">
							Hover over lock types in the Activity grid for detailed explanations of what each lock
							mode means.
						</p>
					</div>
				{/if}
			</div>
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
		{#if selectedDb}
			<span
				class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold {streamWarning
					? 'bg-status-warning/10 text-status-warning border-status-warning/20'
					: 'bg-surface-container text-on-surface-variant border-outline-variant'} border"
			>
				<span
					class="w-1.5 h-1.5 rounded-full {streamWarning
						? 'bg-status-warning'
						: connectedStreams.length > 0
							? 'bg-status-healthy'
							: 'bg-outline'} mr-1.5"
				></span>
				{paused ? 'PAUSED' : streamError ? 'RECONNECTING' : unavailableStreams.length ? 'DATA UNAVAILABLE' : connectedStreams.length === 5 ? 'LIVE' : 'CONNECTING'}
			</span>
		{/if}
		{#if databases.length > 0}
			<button
				onclick={loadDashboard}
				class="flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-lg font-bold text-sm duration-200 ease-in-out hover:brightness-110 active:scale-95 cursor-pointer"
			>
				<span class="material-symbols-outlined text-sm">sync</span>
				Refresh
			</button>
		{/if}
	</div>
</header>

<div class="pt-24 px-container-padding pb-12">
	<div class="overview-intro">
		<div>
			<p class="eyebrow">DATABASE HEALTH</p>
			<h2>Operational overview</h2>
			<p>Connections, workload and contention at a glance.</p>
		</div>
		<p class="data-freshness" aria-live="polite">
			{paused
				? 'Updates paused while this tab is hidden'
				: streamError
					? 'Connection interrupted. Reconnecting…'
					: unavailableStreams.length
						? 'Some live metrics are unavailable. Retrying…'
					: lastUpdated
						? 'Last update ' + lastUpdated.toLocaleTimeString()
						: 'Waiting for live metrics'}
		</p>
	</div>
	{#if waitingLockCount > 0}<a class="attention-banner" href="/activity"
			>{waitingLockCount} waiting locks require attention <span>Investigate activity →</span></a
		>{/if}
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

		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-panel-gap mb-panel-gap">
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
							{activeSessionCount} active
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

		<div class="grid grid-cols-12 gap-panel-gap">
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
							{:else if activeQueries.length === 0}
								<tr>
									<td colspan="4" class="px-4 py-20 text-center text-on-surface-variant text-sm"
										>No active queries in the latest collector samples</td
									>
								</tr>
							{:else}
								{#each activeQueries as query}
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

			<div class="col-span-12 lg:col-span-4 h-[480px] grid grid-rows-2 gap-panel-gap">
				<div
					class="bg-surface-container border border-outline-variant flex flex-col rounded-lg overflow-hidden"
				>
					<div
						class="px-4 py-3 border-b border-outline-variant flex items-center gap-2 bg-surface-container-low"
					>
						<span class="material-symbols-outlined text-error text-sm">lock</span>
						<h2 class="font-headline-md text-headline-md m-0">Live locks</h2>
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
								{waitingLockCount} waiting locks detected
							{/if}
						</p>
					</div>
				</div>

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

		<div
			class="mt-panel-gap rounded-lg border border-outline-variant bg-surface-container-lowest p-4"
		>
			<h2 class="mb-3 text-sm font-bold text-on-surface">PGWarden services</h2>
			<div class="grid gap-3 sm:grid-cols-3">
				{#each ['collector', 'analytics', 'notifier'] as service}
					{@const state = serviceHealth?.services[service as keyof HealthResponse['services']]}
					<div class="rounded-lg border border-outline-variant bg-surface-container p-3">
						<div class="flex items-center justify-between gap-2">
							<span class="capitalize text-sm font-medium text-on-surface">{service}</span>
							<span
								class="flex items-center gap-1 text-xs {state?.status === 'healthy'
									? 'text-status-healthy'
									: 'text-status-danger'}"
							>
								<span
									class="h-2 w-2 rounded-full {state?.status === 'healthy'
										? 'bg-status-healthy'
										: 'bg-status-danger'}"
								></span>
								{state?.status ?? 'unavailable'}
							</span>
						</div>
						<p class="mt-2 text-xs text-on-surface-variant">
							{state?.updated_at
								? `Last heartbeat: ${new Date(state.updated_at).toLocaleTimeString()}`
								: 'No heartbeat received'}
						</p>
					</div>
				{/each}
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

{#if quickActionsOpen}
	<button
		type="button"
		class="fixed inset-0 z-40 cursor-default"
		aria-label="Close quick actions"
		onclick={() => (quickActionsOpen = false)}
	></button>
{/if}

<div class="fixed bottom-5 right-5 z-50 sm:bottom-6 sm:right-6">
	<div class="relative flex flex-col items-end">
		{#if quickActionsOpen}
			<div
				transition:fly={{ y: 12, duration: 180 }}
				class="mb-3 w-72 overflow-hidden rounded-2xl border border-outline-variant/80 bg-surface-container p-2 shadow-floating"
				role="menu"
				aria-label="Quick actions"
			>
				<div class="px-3 pb-2 pt-1">
					<p class="text-xs font-bold uppercase tracking-[0.16em] text-on-surface-variant">
						Quick actions
					</p>
					<p class="mt-1 text-xs text-on-surface-variant">
						{servers.length === 0
							? 'Add a server connection to unlock the workspace.'
							: 'Continue from your current database.'}
					</p>
				</div>

				{#if servers.length === 0}
					<button
						type="button"
						role="menuitem"
						onclick={() => runQuickAction('link')}
						class="quick-action"
					>
						<span class="quick-action-icon text-primary"
							><span class="material-symbols-outlined">add_link</span></span
						>
						<span class="min-w-0 flex-1 text-left">
							<span class="block text-sm font-semibold text-on-surface">Create link</span>
							<span class="mt-0.5 block text-xs text-on-surface-variant"
								>Connect your first PostgreSQL server</span
							>
						</span>
						<span class="material-symbols-outlined text-on-surface-variant">arrow_forward</span>
					</button>
				{:else}
					<button
						type="button"
						role="menuitem"
						onclick={() => runQuickAction('alert')}
						class="quick-action"
					>
						<span class="quick-action-icon text-error"
							><span class="material-symbols-outlined">add_alert</span></span
						>
						<span class="min-w-0 flex-1 text-left">
							<span class="block text-sm font-semibold text-on-surface">Create alert</span>
							<span class="mt-0.5 block text-xs text-on-surface-variant"
								>Set a monitoring threshold</span
							>
						</span>
						<span class="material-symbols-outlined text-on-surface-variant">arrow_forward</span>
					</button>
					<button
						type="button"
						role="menuitem"
						onclick={() => runQuickAction('metrics')}
						class="quick-action"
					>
						<span class="quick-action-icon text-primary"
							><span class="material-symbols-outlined">insights</span></span
						>
						<span class="min-w-0 flex-1 text-left">
							<span class="block text-sm font-semibold text-on-surface">Study metrics</span>
							<span class="mt-0.5 block text-xs text-on-surface-variant"
								>Explore performance signals</span
							>
						</span>
						<span class="material-symbols-outlined text-on-surface-variant">arrow_forward</span>
					</button>
					<button
						type="button"
						role="menuitem"
						onclick={() => runQuickAction('docs')}
						class="quick-action"
					>
						<span class="quick-action-icon text-tertiary"
							><span class="material-symbols-outlined">menu_book</span></span
						>
						<span class="min-w-0 flex-1 text-left">
							<span class="block text-sm font-semibold text-on-surface">Show documentation</span>
							<span class="mt-0.5 block text-xs text-on-surface-variant"
								>Review the current schema</span
							>
						</span>
						<span class="material-symbols-outlined text-on-surface-variant">arrow_forward</span>
					</button>
					<button
						type="button"
						role="menuitem"
						onclick={() => runQuickAction('link')}
						class="quick-action"
					>
						<span class="quick-action-icon text-primary"
							><span class="material-symbols-outlined">database</span></span
						>
						<span class="min-w-0 flex-1 text-left">
							<span class="block text-sm font-semibold text-on-surface">Create link / database</span
							>
							<span class="mt-0.5 block text-xs text-on-surface-variant"
								>Add another monitored database</span
							>
						</span>
						<span class="material-symbols-outlined text-on-surface-variant">arrow_forward</span>
					</button>
				{/if}
			</div>
		{/if}

		<button
			type="button"
			onclick={() => (quickActionsOpen = !quickActionsOpen)}
			aria-label={quickActionsOpen ? 'Close quick actions' : 'Open quick actions'}
			aria-expanded={quickActionsOpen}
			class="inline-flex h-14 w-14 cursor-pointer items-center justify-center rounded-2xl border border-primary/60 bg-primary text-on-primary shadow-floating transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg active:translate-y-0"
		>
			<span
				class="material-symbols-outlined text-[28px] transition-transform duration-200 {quickActionsOpen
					? 'rotate-45'
					: ''}">add</span
			>
		</button>
	</div>
</div>

<style>
	.quick-action {
		display: flex;
		width: 100%;
		align-items: center;
		gap: 0.75rem;
		border-radius: 0.75rem;
		padding: 0.75rem;
		transition:
			background-color 150ms ease,
			transform 150ms ease;
	}
	.quick-action:hover {
		background: var(--color-surface-container-highest);
		transform: translateX(-2px);
	}
	.quick-action:focus-visible {
		outline: 2px solid var(--color-primary);
		outline-offset: -2px;
	}
	.quick-action-icon {
		display: inline-flex;
		height: 2.25rem;
		width: 2.25rem;
		flex-shrink: 0;
		align-items: center;
		justify-content: center;
		border-radius: 0.75rem;
		background: color-mix(in srgb, currentColor 12%, transparent);
	}
</style>
