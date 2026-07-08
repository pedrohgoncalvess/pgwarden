<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		listDatabases,
		listDatabaseConfigs,
		listServers,
		patchDatabaseConfig,
		type DatabaseConfigItem,
		type DatabaseListItem,
		type ServerListItem
	} from '$lib/api';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';

	type IntervalUnit = 'seconds' | 'minutes' | 'hours' | 'days';
	type IntervalDraft = { value: number; unit: IntervalUnit; is_active: boolean };

	const unitOptions: { value: IntervalUnit; label: string; seconds: number }[] = [
		{ value: 'seconds', label: 'Seconds', seconds: 1 },
		{ value: 'minutes', label: 'Minutes', seconds: 60 },
		{ value: 'hours', label: 'Hours', seconds: 3600 },
		{ value: 'days', label: 'Days', seconds: 86400 }
	];

	let databases = $state<DatabaseListItem[]>([]);
	let servers = $state<ServerListItem[]>([]);
	let selectedServerIdLocal = $state('');
	let selectedDbId = $state($page.params.database_id ?? '');
	let configs = $state<DatabaseConfigItem[]>([]);
	let drafts = $state<Record<number, IntervalDraft>>({});
	let loading = $state(true);
	let configsLoading = $state(false);
	let savingIntervals = $state(false);
	let error = $state('');

	const selectedDatabase = $derived(
		databases.find((database) => database.id === selectedDbId) ?? null
	);
	const serverDatabases = $derived(
		databases.filter((db) => db.server_id === selectedServerIdLocal)
	);
	const serverIsFixed = $derived(servers.length <= 1);
	const databaseIsFixed = $derived(serverDatabases.length <= 1);
	const changedConfigs = $derived(
		configs.filter(
			(config) =>
				intervalToSeconds(drafts[config.id]) !== config.interval ||
				(drafts[config.id]?.is_active ?? true) !== !config.is_paused
		)
	);
	const hasChanges = $derived(changedConfigs.length > 0);

	async function load() {
		try {
			loading = true;
			error = '';
			[servers, databases] = await Promise.all([listServers(), listDatabases()]);
			const database = databases.find((db) => db.id === selectedDbId);
			if (!database) {
				const fallbackDb = databases[0];
				if (fallbackDb) {
					selectedDbId = fallbackDb.id;
					selectedServerIdLocal = fallbackDb.server_id;
					selectedServerId.set(selectedServerIdLocal);
					selectedDatabaseId.set(selectedDbId);
					await goto(`/runs/${selectedDbId}/settings/database`, { replaceState: true });
					await loadConfigs();
				}
				return;
			}
			selectedServerIdLocal = database.server_id;
			selectedServerId.set(selectedServerIdLocal);
			selectedDatabaseId.set(selectedDbId);
			await loadConfigs();
		} catch (err: any) {
			handleError(err, 'Failed to load databases.');
		} finally {
			loading = false;
		}
	}

	async function loadConfigs() {
		if (!selectedDbId) {
			configs = [];
			drafts = {};
			return;
		}

		try {
			configsLoading = true;
			error = '';
			selectedDatabaseId.set(selectedDbId);
			configs = await listDatabaseConfigs(selectedDbId);
			drafts = Object.fromEntries(
				configs.map((config) => [config.id, secondsToDraft(config.interval, !config.is_paused)])
			);
		} catch (err: any) {
			handleError(err, 'Failed to load database collector configs.');
		} finally {
			configsLoading = false;
		}
	}

	async function selectServer() {
		if (!selectedServerIdLocal) return;
		try {
			loading = true;
			error = '';
			selectedServerId.set(selectedServerIdLocal);
			const firstDatabase = databases.find(
				(database) => database.server_id === selectedServerIdLocal
			);
			if (firstDatabase) {
				selectedDbId = firstDatabase.id;
				await goto(`/runs/${selectedDbId}/settings/database`, { replaceState: true });
				selectedDatabaseId.set(selectedDbId);
				await loadConfigs();
			} else {
				selectedDbId = '';
				selectedDatabaseId.set(null);
				configs = [];
				drafts = {};
			}
		} catch (err: any) {
			handleError(err, 'Failed to switch server.');
		} finally {
			loading = false;
		}
	}

	async function selectDatabase() {
		if (!selectedDbId) return;
		try {
			loading = true;
			error = '';
			const database = databases.find((db) => db.id === selectedDbId);
			if (database) {
				selectedServerIdLocal = database.server_id;
				selectedServerId.set(selectedServerIdLocal);
			}
			selectedDatabaseId.set(selectedDbId);
			await goto(`/runs/${selectedDbId}/settings/database`, { replaceState: true });
			await loadConfigs();
		} catch (err: any) {
			handleError(err, 'Failed to switch database.');
		} finally {
			loading = false;
		}
	}

	function updateDraftValue(configId: number, value: number) {
		const current = drafts[configId] ?? { value: 0, unit: 'seconds', is_active: true };
		drafts = { ...drafts, [configId]: { ...current, value } };
	}

	function updateDraftUnit(configId: number, unit: IntervalUnit) {
		const current = drafts[configId] ?? { value: 0, unit: 'seconds', is_active: true };
		drafts = { ...drafts, [configId]: { ...current, unit } };
	}

	function updateDraftActive(configId: number, is_active: boolean) {
		const current = drafts[configId] ?? { value: 0, unit: 'seconds', is_active: true };
		drafts = { ...drafts, [configId]: { ...current, is_active } };
	}

	async function saveChanges() {
		const changes = changedConfigs;
		if (changes.length === 0 || !selectedDbId) return;

		try {
			savingIntervals = true;
			error = '';
			const updates = await Promise.all(
				changes.map((config) =>
					patchDatabaseConfig(selectedDbId, config.id, {
						interval: intervalToSeconds(drafts[config.id]),
						is_paused: !(drafts[config.id]?.is_active ?? true)
					})
				)
			);
			configs = configs.map((config) => updates.find((item) => item.id === config.id) ?? config);
			drafts = Object.fromEntries(
				configs.map((config) => [config.id, secondsToDraft(config.interval, !config.is_paused)])
			);
		} catch (err: any) {
			handleError(err, 'Failed to update interval configs.');
		} finally {
			savingIntervals = false;
		}
	}

	function secondsToDraft(seconds: number, is_active: boolean = true): IntervalDraft {
		if (seconds > 0 && seconds % 86400 === 0)
			return { value: seconds / 86400, unit: 'days', is_active };
		if (seconds > 0 && seconds % 3600 === 0)
			return { value: seconds / 3600, unit: 'hours', is_active };
		if (seconds > 0 && seconds % 60 === 0)
			return { value: seconds / 60, unit: 'minutes', is_active };
		return { value: seconds, unit: 'seconds', is_active };
	}

	function intervalToSeconds(draft: IntervalDraft | undefined) {
		if (!draft || !Number.isFinite(draft.value) || draft.value < 0) return 0;
		return draft.value * (unitOptions.find((unit) => unit.value === draft.unit)?.seconds ?? 1);
	}

	function handleError(err: any, fallback: string) {
		if (err.message?.includes('401')) {
			localStorage.removeItem('token');
			window.location.href = '/login';
			return;
		}
		error = err.message || fallback;
	}

	function formatName(name: string) {
		return name.replace(/_/g, ' ').replace(/^\w/, (char) => char.toUpperCase());
	}

	onMount(() => load());
</script>

<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
>
	<span class="material-symbols-outlined text-on-surface-variant">settings</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Settings</h1>
	<span class="text-on-surface-variant">/</span>
	<span class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest"
		>Collector</span
	>
	<span class="text-on-surface-variant">/</span>
	<span class="font-headline-md text-headline-md text-on-background m-0">Database</span>
</header>

<div class="pt-24 px-container-padding pb-12 space-y-6">
	{#if error}
		<div
			class="p-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
		>
			<span class="material-symbols-outlined text-error">error</span>
			<p class="text-sm text-error">{error}</p>
		</div>
	{/if}

	<section class="settings-card p-5">
		<div class="flex flex-wrap items-center justify-between gap-4">
			<div>
				<div class="flex items-center gap-2 mb-1">
					<span class="material-symbols-outlined text-on-surface-variant text-[18px]">database</span
					>
					<h2 class="font-bold text-on-surface text-base m-0">Database-level collectors</h2>
				</div>
				<p class="text-sm text-on-surface-variant">
					Configure collectors that run independently for each monitored database.
				</p>
			</div>

			<div class="flex flex-wrap items-center gap-3">
				<label class="flex items-center gap-2 text-xs text-on-surface-variant">
					Server
					<select
						bind:value={selectedServerIdLocal}
						onchange={selectServer}
						disabled={loading || serverIsFixed}
						class="min-w-40 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-1.5 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-80"
					>
						{#each servers as server}
							<option value={server.id}>{server.name}</option>
						{/each}
					</select>
				</label>

				<label class="flex items-center gap-2 text-xs text-on-surface-variant">
					Database
					<select
						bind:value={selectedDbId}
						onchange={selectDatabase}
						disabled={loading || databaseIsFixed}
						class="min-w-40 rounded-lg border border-outline-variant bg-surface-container-high px-3 py-1.5 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-80"
					>
						{#each serverDatabases as database}
							<option value={database.id}>{database.name}</option>
						{/each}
					</select>
				</label>

				<button
					onclick={saveChanges}
					disabled={!hasChanges || savingIntervals || configsLoading}
					class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold transition-all active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
				>
					<span class="material-symbols-outlined text-[18px]">save</span>
					{savingIntervals ? 'Updating...' : 'Update'}
				</button>
			</div>
		</div>
	</section>

	{#if loading || configsLoading}
		<div class="settings-card p-6 space-y-4">
			{#each [1, 2, 3] as _}
				<div class="skeleton h-16 w-full"></div>
			{/each}
		</div>
	{:else if databases.length === 0}
		<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
			<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3"
				>database</span
			>
			<p class="text-on-surface font-bold mb-1">No databases registered</p>
			<p class="text-sm text-on-surface-variant">
				Connect a database before configuring collectors.
			</p>
		</div>
	{:else if !selectedDatabase}
		<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
			<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3"
				>search_off</span
			>
			<p class="text-on-surface font-bold mb-1">Database not found</p>
			<p class="text-sm text-on-surface-variant">Select another database to manage collectors.</p>
		</div>
	{:else}
		<div class="settings-card overflow-hidden">
			{#each configs as config (config.id)}
				{@const draft = drafts[config.id] ?? secondsToDraft(config.interval, !config.is_paused)}
				<div class="row-item px-5 py-4 flex items-center justify-between gap-4">
					<div class="min-w-0">
						<p class="font-bold text-on-surface text-sm truncate">{formatName(config.name)}</p>
					</div>

					<div class="flex items-center gap-4 flex-shrink-0">
						<div class="flex items-center gap-2">
							<label class="text-xs text-on-surface-variant" for={`interval-${config.id}`}
								>Interval</label
							>
							<input
								id={`interval-${config.id}`}
								type="number"
								min="0"
								step="0.5"
								value={draft.value}
								disabled={savingIntervals}
								oninput={(event) => updateDraftValue(config.id, Number(event.currentTarget.value))}
								class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
							<select
								value={draft.unit}
								disabled={savingIntervals}
								onchange={(event) =>
									updateDraftUnit(config.id, event.currentTarget.value as IntervalUnit)}
								class="bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							>
								{#each unitOptions as unit}
									<option value={unit.value}>{unit.label}</option>
								{/each}
							</select>
						</div>

						<label class="flex items-center gap-2 text-xs font-bold text-on-surface">
							<input
								type="checkbox"
								checked={draft.is_active}
								disabled={savingIntervals}
								onchange={(event) => updateDraftActive(config.id, event.currentTarget.checked)}
								class="accent-primary"
							/>
							Active
						</label>
					</div>
				</div>
			{:else}
				<div class="px-6 py-8 text-center text-sm text-on-surface-variant">
					No database collector configs found.
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.settings-card {
		background: rgba(26, 33, 31, 0.95);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 14px;
	}
	.row-item {
		border-bottom: 1px solid rgba(133, 148, 144, 0.08);
	}
	.row-item:last-child {
		border-bottom: none;
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
		border-radius: 8px;
	}
	@keyframes skeleton-shine {
		0% {
			background-position: 200% 0;
		}
		100% {
			background-position: -200% 0;
		}
	}
</style>
