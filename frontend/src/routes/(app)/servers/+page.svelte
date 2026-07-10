<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { listServers, listDatabases, createSessionEventSource } from '$lib/api';
	import type { ServerListItem, DatabaseListItem, SessionMetric } from '$lib/api';

	
	let servers = $state<ServerListItem[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let loading = $state(true);
	let error = $state('');

	
	let dbSessions = $state<Record<string, SessionMetric[] | null>>({});
	let eventSources = $state<Record<string, EventSource>>({});

	
	let expanded = $state<Record<string, boolean>>({});

	
	function getDatabasesForServer(serverId: string): DatabaseListItem[] {
		return databases.filter((db) => db.server_id === serverId);
	}

	function sessionCount(dbId: string): number {
		const s = dbSessions[dbId];
		return s ? s.length : 0;
	}

	function activeCount(dbId: string): number {
		const s = dbSessions[dbId];
		return s ? s.filter((x) => x.state === 'active').length : 0;
	}

	function waitingCount(dbId: string): number {
		const s = dbSessions[dbId];
		return s ? s.filter((x) => x.wait_event !== null).length : 0;
	}

	function formatDuration(value: string | null): string {
		if (!value) return '--';
		const ms = Date.now() - new Date(value).getTime();
		if (isNaN(ms) || ms < 0) return '--';
		const s = Math.floor(ms / 1000);
		if (s < 60) return `${s}s`;
		const m = Math.floor(s / 60);
		if (m < 60) return `${m}m ${s % 60}s`;
		const h = Math.floor(m / 60);
		return `${h}h ${m % 60}m`;
	}

	function getStatusColor(status: string): string {
		if (status === 'healthy') return 'text-primary';
		if (status === 'pending') return 'text-tertiary';
		return 'text-error';
	}

	function getStatusIcon(status: string): string {
		if (status === 'healthy') return 'check_circle';
		if (status === 'pending') return 'hourglass_empty';
		return 'error';
	}

	function getStatusBadge(status: string): string {
		if (status === 'healthy') return 'bg-primary/10 text-primary border-primary/20';
		if (status === 'pending') return 'bg-tertiary/10 text-tertiary border-tertiary/20';
		return 'bg-error/10 text-error border-error/20';
	}

	function getStateChip(state: string | null): string {
		if (state === 'active') return 'bg-primary/15 text-primary';
		if (state === 'idle') return 'bg-outline/20 text-on-surface-variant';
		if (state === 'idle in transaction') return 'bg-tertiary/15 text-tertiary';
		return 'bg-outline/10 text-on-surface-variant';
	}

	
	function connectDbStream(dbId: string) {
		if (eventSources[dbId]) {
			eventSources[dbId].close();
		}
		dbSessions[dbId] = null; 
		const es = createSessionEventSource(dbId);
		es.addEventListener('sessions', (event) => {
			try {
				dbSessions[dbId] = JSON.parse((event as MessageEvent).data);
			} catch {
				
			}
		});
		es.onerror = () => {
			
		};
		eventSources[dbId] = es;
	}

	function disconnectAllStreams() {
		for (const es of Object.values(eventSources)) {
			es.close();
		}
		eventSources = {};
	}

	
	async function load() {
		try {
			loading = true;
			error = '';
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);

			
			if (servers.length > 0) {
				expanded[servers[0].id] = true;
			}

			
			for (const db of databases) {
				connectDbStream(db.id);
			}
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load connections.';
		} finally {
			loading = false;
		}
	}

	function toggleExpand(serverId: string) {
		expanded[serverId] = !expanded[serverId];
	}

	
	onMount(() => load());
	onDestroy(() => disconnectAllStreams());
</script>


<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex justify-between items-center px-container-padding h-16"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">lan</span>
		<h1 class="font-headline-md text-headline-md text-on-background m-0">Connections</h1>
		{#if !loading}
			<span
				class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-primary/10 text-primary border border-primary/20"
			>
				<span class="w-1.5 h-1.5 rounded-full bg-primary mr-1.5 pulse-dot"></span>
				{servers.length} SERVER{servers.length !== 1 ? 'S' : ''}
			</span>
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

	{#if loading}
		
		<div class="space-y-4">
			{#each [1, 2] as _}
				<div class="server-card p-6">
					<div class="flex items-center justify-between">
						<div class="flex items-center gap-4">
							<div class="skeleton w-10 h-10 rounded-xl"></div>
							<div class="space-y-2">
								<div class="skeleton h-4 w-40"></div>
								<div class="skeleton h-3 w-24"></div>
							</div>
						</div>
						<div class="skeleton h-6 w-20 rounded-full"></div>
					</div>
				</div>
			{/each}
		</div>
	{:else if servers.length === 0}
		
		<div class="flex flex-col items-center justify-center py-24">
			<div
				class="w-20 h-20 rounded-2xl bg-surface-container-high border border-outline-variant flex items-center justify-center mb-6"
			>
				<span class="material-symbols-outlined text-[40px] text-on-surface-variant">lan</span>
			</div>
			<h2 class="font-headline-md text-headline-md font-bold text-on-surface mb-2">
				No servers registered
			</h2>
			<p class="text-body-md text-on-surface-variant max-w-md text-center mb-8">
				Register a PostgreSQL server from the main dashboard to start monitoring live connections.
			</p>
		</div>
	{:else}
		
		<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
			<div class="bg-surface-container border border-outline-variant p-4 rounded-lg">
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>SERVERS</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-primary font-mono">{servers.length}</span>
					<span class="text-on-surface-variant text-[10px]">
						{servers.filter((s) => s.status === 'healthy').length} healthy
					</span>
				</div>
			</div>
			<div class="bg-surface-container border border-outline-variant p-4 rounded-lg">
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>DATABASES</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-on-surface font-mono"
						>{databases.length}</span
					>
					<span class="text-on-surface-variant text-[10px]">monitored</span>
				</div>
			</div>
			<div class="bg-surface-container border border-outline-variant p-4 rounded-lg">
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>TOTAL SESSIONS</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-tertiary font-mono">
						{Object.values(dbSessions).reduce((acc, s) => acc + (s?.length ?? 0), 0)}
					</span>
					<span class="text-on-surface-variant text-[10px]">live</span>
				</div>
			</div>
			<div class="bg-surface-container border border-outline-variant p-4 rounded-lg">
				<span class="text-on-surface-variant font-label-caps text-label-caps tracking-widest"
					>WAITING</span
				>
				<div class="flex items-end justify-between mt-1">
					<span class="font-metric-lg text-metric-lg text-error font-mono">
						{Object.values(dbSessions).reduce(
							(acc, s) => acc + (s ? s.filter((x) => x.wait_event !== null).length : 0),
							0
						)}
					</span>
					<span class="text-on-surface-variant text-[10px]">blocked</span>
				</div>
			</div>
		</div>

		
		<div class="space-y-4">
			{#each servers as server (server.id)}
				{@const serverDbs = getDatabasesForServer(server.id)}
				{@const isOpen = !!expanded[server.id]}
				{@const totalSessions = serverDbs.reduce((a, db) => a + sessionCount(db.id), 0)}
				{@const totalWaiting = serverDbs.reduce((a, db) => a + waitingCount(db.id), 0)}

				<div class="server-card overflow-hidden">
					
					<button
						onclick={() => toggleExpand(server.id)}
						class="w-full flex items-center justify-between px-6 py-5 cursor-pointer text-left hover:bg-white/[0.02] transition-colors"
					>
						<div class="flex items-center gap-4">
							
							<div
								class="w-10 h-10 rounded-xl bg-surface-container-high border border-outline-variant/50 flex items-center justify-center flex-shrink-0"
							>
								<span
									class="material-symbols-outlined {getStatusColor(server.status)} text-[20px]"
									style="font-variation-settings: 'FILL' 1;"
								>
									{getStatusIcon(server.status)}
								</span>
							</div>

							<div>
								<div class="flex items-center gap-3">
									<h2 class="font-headline-md text-headline-md font-bold text-on-surface m-0">
										{server.name}
									</h2>
									<span
										class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border {getStatusBadge(
											server.status
										)} uppercase"
									>
										{#if server.status === 'healthy'}
											<span class="w-1.5 h-1.5 rounded-full bg-current mr-1.5 pulse-dot"></span>
										{/if}
										{server.status}
									</span>
								</div>
								<p class="text-[11px] text-on-surface-variant mt-0.5">
									{serverDbs.length} database{serverDbs.length !== 1 ? 's' : ''} · {totalSessions} session{totalSessions !==
									1
										? 's'
										: ''}
									{#if totalWaiting > 0}
										· <span class="text-error font-bold">{totalWaiting} waiting</span>
									{/if}
								</p>
							</div>
						</div>

						<div class="flex items-center gap-4">
							
							{#if totalSessions > 0}
								<div class="hidden sm:flex items-center gap-2">
									<div
										class="flex items-center gap-1.5 px-3 py-1 bg-primary/10 border border-primary/20 rounded-full"
									>
										<span class="w-1.5 h-1.5 rounded-full bg-primary pulse-dot"></span>
										<span class="text-[11px] font-bold text-primary">{totalSessions} live</span>
									</div>
									{#if totalWaiting > 0}
										<div
											class="flex items-center gap-1.5 px-3 py-1 bg-error/10 border border-error/20 rounded-full"
										>
											<span class="material-symbols-outlined text-error text-[12px]">block</span>
											<span class="text-[11px] font-bold text-error">{totalWaiting}</span>
										</div>
									{/if}
								</div>
							{/if}
							<span
								class="material-symbols-outlined text-on-surface-variant chevron-anim"
								style="transform: rotate({isOpen ? 180 : 0}deg)"
							>
								expand_more
							</span>
						</div>
					</button>

					
					{#if isOpen}
						<div class="border-t border-outline-variant/30 px-6 pb-6 pt-4 space-y-4">
							{#if serverDbs.length === 0}
								<p class="text-sm text-on-surface-variant text-center py-4">
									No databases linked to this server.
								</p>
							{:else}
								{#each serverDbs as db (db.id)}
									{@const sessions = dbSessions[db.id]}
									{@const sCount = sessionCount(db.id)}
									{@const aCount = activeCount(db.id)}
									{@const wCount = waitingCount(db.id)}

									<div class="db-row overflow-hidden">
										
										<div
											class="flex items-center justify-between px-4 py-3 border-b border-outline-variant/20"
										>
											<div class="flex items-center gap-3">
												<span
													class="material-symbols-outlined text-primary text-[16px]"
													style="font-variation-settings: 'FILL' 1;">database</span
												>
												<span class="font-code-sm text-code-sm font-bold text-on-surface"
													>{db.name}</span
												>
												{#if !db.status}
													<span
														class="text-[10px] px-1.5 py-0.5 bg-error/10 text-error border border-error/20 rounded font-bold uppercase"
														>inactive</span
													>
												{/if}
											</div>
											<div class="flex items-center gap-3">
												{#if sessions === null}
													<span class="text-[10px] text-on-surface-variant animate-pulse"
														>connecting…</span
													>
												{:else}
													<span class="text-[10px] text-on-surface-variant">
														<span class="text-primary font-bold">{sCount}</span> total ·
														<span class="text-tertiary font-bold">{aCount}</span>
														active
														{#if wCount > 0}· <span class="text-error font-bold">{wCount}</span> waiting{/if}
													</span>
												{/if}
												<div
													class="w-1.5 h-1.5 rounded-full {sessions === null
														? 'bg-tertiary animate-pulse'
														: sCount > 0
															? 'bg-primary pulse-dot'
															: 'bg-outline'}"
												></div>
											</div>
										</div>

										
										<div class="overflow-x-auto">
											<table class="w-full text-left border-collapse">
												<thead>
													<tr class="bg-surface-container-lowest/60">
														<th
															class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
															>PID</th
														>
														<th
															class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
															>USER</th
														>
														<th
															class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
															>STATE</th
														>
														<th
															class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
															>DURATION</th
														>
														<th
															class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] tracking-widest"
															>QUERY</th
														>
														<th
															class="px-4 py-2 font-label-caps text-on-surface-variant text-[10px] tracking-widest text-center"
															>WAIT</th
														>
													</tr>
												</thead>
												<tbody class="divide-y divide-outline-variant/20">
													{#if sessions === null}
														<tr>
															<td colspan="6" class="px-4 py-5 text-center">
																<div
																	class="flex items-center justify-center gap-2 text-on-surface-variant text-sm"
																>
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
																	Connecting to stream…
																</div>
															</td>
														</tr>
													{:else if sessions.length === 0}
														<tr>
															<td
																colspan="6"
																class="px-4 py-5 text-center text-on-surface-variant text-sm"
															>
																<div class="flex items-center justify-center gap-2">
																	<span class="material-symbols-outlined text-primary text-[16px]"
																		>check_circle</span
																	>
																	No active sessions
																</div>
															</td>
														</tr>
													{:else}
														{#each sessions as session (session.pid)}
															<tr class="session-row">
																<td
																	class="px-4 py-2.5 font-code-sm text-code-sm text-on-surface-variant"
																	>{session.pid}</td
																>
																<td class="px-4 py-2.5 font-code-sm text-code-sm text-on-surface"
																	>{session.user_name || '--'}</td
																>
																<td class="px-4 py-2.5">
																	<span
																		class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold {getStateChip(
																			session.state
																		)}"
																	>
																		{session.state || '--'}
																	</span>
																</td>
																<td
																	class="px-4 py-2.5 font-code-sm text-code-sm {session.state ===
																	'active'
																		? 'text-tertiary font-bold'
																		: 'text-on-surface-variant'}"
																>
																	{formatDuration(session.query_start)}
																</td>
																<td class="px-4 py-2.5 max-w-xs">
																	<code
																		class="font-code-sm text-code-sm text-on-surface block truncate max-w-[300px]"
																	>
																		{session.query_preview || session.application_name || '--'}
																	</code>
																</td>
																<td class="px-4 py-2.5 text-center">
																	{#if session.wait_event}
																		<span
																			class="material-symbols-outlined text-error text-[16px]"
																			title="{session.wait_event_type}: {session.wait_event}"
																			>block</span
																		>
																	{:else}
																		<span class="material-symbols-outlined text-primary text-[16px]"
																			>check</span
																		>
																	{/if}
																</td>
															</tr>
														{/each}
													{/if}
												</tbody>
											</table>
										</div>
									</div>
								{/each}
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.server-card {
		background: rgba(26, 33, 31, 0.95);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 14px;
		transition: border-color 0.2s ease;
	}
	.server-card:hover {
		border-color: rgba(133, 148, 144, 0.3);
	}
	.db-row {
		background: rgba(14, 21, 19, 0.6);
		border: 1px solid rgba(133, 148, 144, 0.1);
		border-radius: 10px;
		transition: background 0.2s ease;
	}
	.db-row:hover {
		background: rgba(14, 21, 19, 0.8);
	}
	.session-row {
		transition: background 0.15s ease;
	}
	.session-row:hover {
		background: rgba(133, 148, 144, 0.05);
	}
	.pulse-dot {
		animation: pulse-ring 2s ease-in-out infinite;
	}
	@keyframes pulse-ring {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.4;
		}
	}
	.skeleton {
		background: linear-gradient(
			90deg,
			rgba(133, 148, 144, 0.08) 25%,
			rgba(133, 148, 144, 0.16) 50%,
			rgba(133, 148, 144, 0.08) 75%
		);
		background-size: 200% 100%;
		animation: skeleton-shine 1.5s infinite;
		border-radius: 4px;
	}
	@keyframes skeleton-shine {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}
	.chevron-anim {
		transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
	}
</style>
