<script lang="ts">
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import {
		createSessionEventSource,
		createLockEventSource,
		createNativeQueryEventSource
	} from '$lib/api';
	import type { SessionMetric, LockMetric, NativeQueryMetric } from '$lib/api';
	let mounted = $state(false);
	let visible = $state(true);
	let tab = $state<'queries' | 'sessions' | 'locks'>('queries');
	let search = $state('');
	let queries = $state<NativeQueryMetric[] | null>(null);
	let sessions = $state<SessionMetric[] | null>(null);
	let locks = $state<LockMetric[] | null>(null);
	let status = $state('Connecting');
	let updated = $state<Date | null>(null);
	let failed = $state<number[]>([]);
	$effect(() => {
		void $selectedDatabaseId;
		queries = null;
		sessions = null;
		locks = null;
		updated = null;
	});
	const waiting = $derived(locks?.filter((lock) => lock.is_granted === false).length ?? 0);
	const needle = $derived(search.toLowerCase());
	const queryRows = $derived(
		(queries ?? [])
			.filter(
				(row) =>
					row.state === 'active' &&
					`${row.query} ${row.pid} ${row.user_name}`.toLowerCase().includes(needle)
			)
			.sort((a, b) => (b.query_duration_ms ?? 0) - (a.query_duration_ms ?? 0))
	);
	const sessionRows = $derived(
		(sessions ?? []).filter((row) =>
			`${row.query_preview} ${row.pid} ${row.user_name} ${row.state}`.toLowerCase().includes(needle)
		)
	);
	const lockRows = $derived(
		(locks ?? [])
			.filter((row) =>
				`${row.mode} ${row.holder_pid} ${row.query_preview}`.toLowerCase().includes(needle)
			)
			.sort((a, b) => Number(a.is_granted) - Number(b.is_granted))
	);
	const count = $derived(
		tab === 'queries' ? queryRows.length : tab === 'sessions' ? sessionRows.length : lockRows.length
	);
	let limit = $state(100);
	onMount(() => {
		mounted = true;
		const change = () => {
			visible = document.visibilityState === 'visible';
		};
		change();
		document.addEventListener('visibilitychange', change);
		return () => document.removeEventListener('visibilitychange', change);
	});
	$effect(() => {
		void $selectedDatabaseId;
		void tab;
		void search;
		limit = 100;
	});
	$effect(() => {
		const databaseId = $selectedDatabaseId;
		if (!mounted || !databaseId || !visible) return;
		status = 'Connecting';
		const sources = [
			createNativeQueryEventSource(databaseId),
			createSessionEventSource(databaseId),
			createLockEventSource(databaseId)
		];
		const handlers = [
			(event: Event) => {
				queries = JSON.parse((event as MessageEvent).data);
			},
			(event: Event) => {
				sessions = JSON.parse((event as MessageEvent).data);
			},
			(event: Event) => {
				locks = JSON.parse((event as MessageEvent).data);
			}
		];
		['native_query', 'sessions', 'locks'].forEach((name, index) => {
			sources[index].addEventListener(name, (event) => {
				try {
					handlers[index](event);
					updated = new Date();
					failed = failed.filter((item) => item !== index);
					status = failed.length ? 'Reconnecting' : 'Live';
				} catch {
					status = 'Unable to read live data';
				}
			});
			sources[index].onerror = () => {
				failed = [...new Set([...failed, index])];
				status = 'Reconnecting';
			};
		});
		return () => sources.forEach((source) => source.close());
	});
</script>

<header
	class="app-page-header fixed right-0 z-40 flex items-center justify-between border-b border-outline-variant px-container-padding"
>
	<h1 class="text-headline-md font-semibold">Activity</h1>
	<span class="data-freshness" aria-live="polite"
		>{visible ? status : 'Paused'}{updated ? ` · ${updated.toLocaleTimeString()}` : ''}</span
	>
</header>
<div class="px-container-padding pt-24 pb-12">
	<div class="overview-intro">
		<div>
			<p class="eyebrow">LIVE WORKLOAD</p>
			<h2>Investigate database activity</h2>
			<p>Active queries, connected sessions and lock contention.</p>
		</div>
		<span class="text-sm text-status-warning">{waiting} waiting locks</span>
	</div>
	{#if !$selectedDatabaseId}
		<div class="empty-state">
			<span class="material-symbols-outlined">database</span>
			<h2>Select a database</h2>
			<p>Choose a server and database above to inspect live activity.</p>
			<a href={resolve('/search')}>Find a database →</a>
		</div>
	{:else}
		<div class="activity-controls">
			<div class="activity-tabs" role="group" aria-label="Activity view">
				{#each ['queries', 'sessions', 'locks'] as view (view)}<button
						class:chosen={tab === view}
						aria-pressed={tab === view}
						onclick={() => (tab = view as typeof tab)}
						>{view === 'queries'
							? 'Active queries'
							: view === 'sessions'
								? 'Sessions'
								: 'Locks'}</button
					>{/each}
			</div>
			<input
				aria-label="Filter activity"
				placeholder="Filter by SQL, user or PID…"
				bind:value={search}
			/>
		</div>
		<div class="activity-table">
			<table>
				<thead
					><tr
						><th>PID</th><th>{tab === 'locks' ? 'Lock mode' : 'User'}</th><th
							>{tab === 'queries' ? 'Duration' : 'State'}</th
						><th>SQL / Details</th></tr
					></thead
				><tbody>
					{#if tab === 'queries'}
						{#each queryRows.slice(0, limit) as row (`${row.pid}:${row.backend_start}:${row.collected_at}`)}<tr
								><td>{row.pid}</td><td>{row.user_name ?? '—'}</td><td
									>{row.query_duration_ms == null
										? '—'
										: `${Math.round(row.query_duration_ms)} ms`}</td
								><td
									><details>
										<summary>{row.query?.slice(0, 160)}</summary>
										<pre>{row.query}</pre>
									</details></td
								></tr
							>{/each}
					{:else if tab === 'sessions'}
						{#each sessionRows.slice(0, limit) as row (`${row.pid}:${row.backend_start}`)}<tr
								><td>{row.pid}</td><td>{row.user_name ?? '—'}</td><td>{row.state ?? '—'}</td><td
									>{row.query_preview ?? row.application_name ?? '—'}</td
								></tr
							>{/each}
					{:else}
						{#each lockRows.slice(0, limit) as row, index (index)}<tr
								><td>{row.holder_pid}</td><td>{row.mode}</td><td
									class:text-status-warning={row.is_granted === false}
									>{row.is_granted === false
										? 'Waiting'
										: row.is_granted
											? 'Granted'
											: 'Unknown'}</td
								><td>{row.query_preview ?? `Table #${row.table_id}`}</td></tr
							>{/each}
					{/if}
				</tbody>
			</table>
			{#if count === 0}<div class="empty-state">
					<h2>
						{(tab === 'queries' ? queries : tab === 'sessions' ? sessions : locks) === null
							? 'Waiting for live data'
							: search
								? 'No matching activity'
								: `No ${tab === 'queries' ? 'active queries' : tab}`}
					</h2>
					<p>{search ? 'Try another filter.' : 'New activity will appear automatically.'}</p>
				</div>{/if}
		</div>
		<div class="activity-footer">
			<span>{Math.min(count, limit)} of {count} results</span>{#if count > limit}<button
					onclick={() => (limit += 100)}>Show 100 more</button
				>{/if}
		</div>
	{/if}
</div>

<style>
	.activity-controls {
		display: flex;
		justify-content: space-between;
		gap: 16px;
		flex-wrap: wrap;
		margin-bottom: 16px;
	}
	.activity-tabs {
		display: flex;
		gap: 4px;
		padding: 4px;
		background: var(--color-surface-container);
		border: 1px solid var(--color-outline-variant);
		border-radius: 6px;
	}
	.activity-tabs button {
		padding: 6px 12px;
		border-radius: 3px;
		color: var(--color-on-surface-variant);
		font-size: 12px;
	}
	.activity-tabs .chosen {
		background: var(--color-surface-container-highest);
		color: var(--color-on-surface);
	}
	input {
		min-width: 240px;
		padding: 8px 12px;
		border: 1px solid var(--color-outline-variant);
		border-radius: 5px;
		background: var(--color-surface-container-low);
		font-size: 12px;
	}
	.activity-table {
		overflow: auto;
		border: 1px solid var(--color-outline-variant);
		border-radius: 6px;
		background: var(--color-surface-container-low);
	}
	table {
		width: 100%;
		border-collapse: collapse;
		text-align: left;
		font-size: 12px;
	}
	th {
		padding: 12px 16px;
		border-bottom: 1px solid var(--color-outline-variant);
		white-space: nowrap;
	}
	td {
		padding: 12px 16px;
		font-family: var(--font-mono);
		border-bottom: 1px solid color-mix(in srgb, var(--color-outline-variant) 40%, transparent);
		vertical-align: top;
	}
	td:last-child {
		min-width: 280px;
		max-width: 720px;
		overflow-wrap: anywhere;
	}
	pre {
		white-space: pre-wrap;
		margin-top: 12px;
		color: var(--color-on-surface-variant);
	}
	summary {
		cursor: pointer;
	}
	.empty-state {
		text-align: center;
		padding: 56px 24px;
		color: var(--color-on-surface-variant);
		font-size: 13px;
	}
	.empty-state h2 {
		color: var(--color-on-surface);
		font-size: 16px;
		margin-bottom: 8px;
	}
	.empty-state a {
		display: inline-block;
		margin-top: 16px;
		color: var(--color-primary);
	}
	.activity-footer {
		display: flex;
		justify-content: space-between;
		padding: 16px 0;
		color: var(--color-on-surface-variant);
		font-size: 12px;
	}
	.activity-footer button {
		color: var(--color-primary);
	}
</style>
