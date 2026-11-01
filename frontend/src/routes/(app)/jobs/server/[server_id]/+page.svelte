<script lang="ts">
	import { profile, can } from '$lib/access';
	import Select from '$lib/components/Select.svelte';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		listServers,
		listServerConfigs,
		patchServerConfig,
		type ServerConfigItem,
		type ServerListItem
	} from '$lib/api';
	import { selectedServerId as selectedServerIdStore } from '$lib/stores/selectedServer';

	type IntervalUnit = 'seconds' | 'minutes' | 'hours' | 'days';
	type IntervalDraft = { value: number; unit: IntervalUnit; is_active: boolean };

	const unitOptions: { value: IntervalUnit; label: string; seconds: number }[] = [
		{ value: 'seconds', label: 'Seconds', seconds: 1 },
		{ value: 'minutes', label: 'Minutes', seconds: 60 },
		{ value: 'hours', label: 'Hours', seconds: 3600 },
		{ value: 'days', label: 'Days', seconds: 86400 }
	];

	let servers = $state<ServerListItem[]>([]);
	let selectedServerId = $state($page.params.server_id ?? '');
	let configs = $state<ServerConfigItem[]>([]);
	let drafts = $state<Record<number, IntervalDraft>>({});
	let loading = $state(true);
	let configsLoading = $state(false);
	let savingIntervals = $state(false);
	let error = $state('');

	const selectedServer = $derived(servers.find((server) => server.id === selectedServerId) ?? null);
	const serverIsFixed = $derived(servers.length <= 1);
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
			servers = await listServers();
			if (!servers.some((server) => server.id === selectedServerId)) {
				if (servers[0]) {
					selectedServerId = servers[0].id;
					selectedServerIdStore.set(selectedServerId);
					await goto(`/jobs/server/${selectedServerId}`, { replaceState: true });
					await loadConfigs();
				}
				return;
			}
			selectedServerIdStore.set(selectedServerId);
			await loadConfigs();
		} catch (err: any) {
			handleError(err, 'Failed to load servers.');
		} finally {
			loading = false;
		}
	}

	async function loadConfigs() {
		if (!selectedServerId) {
			configs = [];
			drafts = {};
			return;
		}

		try {
			configsLoading = true;
			error = '';
			configs = await listServerConfigs(selectedServerId);
			drafts = Object.fromEntries(
				configs.map((config) => [config.id, secondsToDraft(config.interval, !config.is_paused)])
			);
		} catch (err: any) {
			handleError(err, 'Failed to load server collector configs.');
		} finally {
			configsLoading = false;
		}
	}

	function selectServer() {
		if (!selectedServerId) return;
		selectedServerIdStore.set(selectedServerId);
		goto(`/jobs/server/${selectedServerId}`);
		loadConfigs();
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
		if (changes.length === 0 || !selectedServerId) return;

		try {
			savingIntervals = true;
			error = '';
			const updates = await Promise.all(
				changes.map((config) =>
					patchServerConfig(selectedServerId, config.id, {
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
			handleError(err, 'Failed to update configs.');
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
	class="fixed top-0 right-0 app-page-header z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
>
	<span class="material-symbols-outlined text-on-surface-variant">settings</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Settings</h1>
	<span class="text-on-surface-variant">/</span>
	<span class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest"
		>Collector</span
	>
	<span class="text-on-surface-variant">/</span>
	<span class="font-headline-md text-headline-md text-on-background m-0">Server</span>
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
					<span class="material-symbols-outlined text-on-surface-variant text-[18px]">dns</span>
					<h2 class="font-bold text-on-surface text-base m-0">Server-level collectors</h2>
				</div>
				<p class="text-sm text-on-surface-variant">
					Configure collectors that run once per monitored server.
				</p>
			</div>

			<div class="flex flex-wrap items-center gap-3">
				<label class="flex items-center gap-2 text-xs text-on-surface-variant">
					Server
					<Select
						bind:value={selectedServerId}
						onchange={selectServer}
						disabled={loading || serverIsFixed}
						class="min-w-40"
						aria-label="Server"
						options={servers.map((item) => ({ value: item.id, label: item.name }))}
					/>
				</label>

				<button
					onclick={saveChanges}
					disabled={!can($profile, 'schedulers.configure') ||
						!hasChanges ||
						savingIntervals ||
						configsLoading}
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
	{:else if servers.length === 0}
		<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
			<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3">dns</span>
			<p class="text-on-surface font-bold mb-1">No servers registered</p>
			<p class="text-sm text-on-surface-variant">Add a server before configuring collectors.</p>
		</div>
	{:else if !selectedServer}
		<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
			<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3"
				>search_off</span
			>
			<p class="text-on-surface font-bold mb-1">Server not found</p>
			<p class="text-sm text-on-surface-variant">Select another server to manage collectors.</p>
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
								disabled={!can($profile, 'schedulers.configure') || savingIntervals}
								oninput={(event) => updateDraftValue(config.id, Number(event.currentTarget.value))}
								class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
							<Select
								value={draft.unit}
								disabled={savingIntervals}
								onchange={(value) => updateDraftUnit(config.id, value as IntervalUnit)}
								aria-label="Interval unit"
								options={unitOptions}
							/>
						</div>

						<label class="flex items-center gap-2 text-xs font-bold text-on-surface">
							<input
								type="checkbox" role="switch"
								checked={draft.is_active}
								disabled={!can($profile, 'schedulers.configure') || savingIntervals}
								onchange={(event) => updateDraftActive(config.id, event.currentTarget.checked)}
								
							/>
							Active
						</label>
					</div>
				</div>
			{:else}
				<div class="px-6 py-8 text-center text-sm text-on-surface-variant">
					No server collector configs found.
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
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
