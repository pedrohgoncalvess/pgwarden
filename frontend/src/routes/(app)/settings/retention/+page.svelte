<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { profile } from '$lib/access';
	import Select from '$lib/components/Select.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import RetentionImpact from '$lib/components/retention/RetentionImpact.svelte';
	import RetentionPolicies from '$lib/components/retention/RetentionPolicies.svelte';
	import {
		listRetentionPolicies,
		previewRetention,
		saveRetention,
		previewGlobalRetention,
		saveGlobalRetention,
		initialWindow,
		retentionUnits,
		type RetentionPolicy,
		type RetentionPreview,
		type RetentionUnit
	} from '$lib/retention-api';

	let policies = $state<RetentionPolicy[]>([]);
	let selected = $state('');
	let global = $state(false);
	let value = $state<number | undefined>(90);
	let unit = $state<RetentionUnit>('days');
	let preview = $state<RetentionPreview | null>(null);
	let busy = $state(false);
	let saving = $state(false);
	let refreshing = $state(false);
	let loading = $state(true);
	let error = $state('');
	let success = $state('');
	let revision = 0;
	const policy = $derived(policies.find((item) => item.name === selected));
	const valid = $derived(
		value !== undefined && Number.isInteger(value) && value >= 1 && value <= 100000
	);
	const fresh = $derived(
		preview?.name === (global ? '__all__' : selected) &&
			preview?.window.value === value &&
			preview?.window.unit === unit &&
			valid
	);
	const pausedCount = $derived(
		policies.filter((item) => item.job_id !== null && !item.scheduled).length
	);
	const configuredCount = $derived(policies.filter((item) => item.job_id !== null).length);

	function changeScope() {
		revision++;
		preview = null;
		error = '';
		success = '';
	}

	async function editTable(name: string) {
		global = false;
		select(name);
		await tick();
		document.getElementById('retention-amount')?.focus();
	}

	function select(name: string) {
		revision++;
		selected = name;
		preview = null;
		error = '';
		success = '';
		const current = policies.find((item) => item.name === name);
		if (current) ({ value, unit } = initialWindow(current));
	}

	async function load() {
		loading = policies.length === 0;
		refreshing = true;
		error = '';
		try {
			policies = await listRetentionPolicies();
			preview = null;
			if (policies.length && !policies.some((item) => item.name === selected))
				select(policies[0].name);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not load retention policies.';
		} finally {
			loading = false;
			refreshing = false;
		}
	}

	async function simulate() {
		if (!valid || value === undefined) return;
		const currentRevision = ++revision;
		busy = true;
		error = '';
		success = '';
		try {
			const result = global
				? await previewGlobalRetention({ value, unit })
				: await previewRetention(selected, { value, unit });
			if (currentRevision === revision) preview = result;
		} catch (cause) {
			if (currentRevision === revision) {
				preview = null;
				error = cause instanceof Error ? cause.message : 'Could not estimate storage.';
			}
		} finally {
			busy = false;
		}
	}

	async function save() {
		if (!fresh || !valid || value === undefined || !preview) return;
		busy = true;
		saving = true;
		error = '';
		success = '';
		try {
			if (global) {
				policies = await saveGlobalRetention({ value, unit });
			} else {
				const updated = await saveRetention(selected, { value, unit });
				policies = policies.map((item) => (item.name === updated.name ? updated : item));
			}
			preview = null;
			success = global
				? `Retention policy saved for all ${policies.length} metric tables. TimescaleDB will apply each policy on its scheduled background runs.`
				: 'Retention policy saved. TimescaleDB will apply it on its scheduled background runs.';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not save retention policy.';
		} finally {
			busy = false;
			saving = false;
		}
	}
	onMount(() => {
		if ($profile?.is_admin) void load();
		else loading = false;
	});
</script>

<header
	class="app-page-header fixed right-0 z-40 flex items-center justify-between border-b border-outline-variant px-container-padding"
>
	<div class="flex min-w-0 items-center gap-3">
		<span class="material-symbols-outlined text-on-surface-variant" aria-hidden="true">history</span
		>
		<h1 class="m-0 font-headline-md text-headline-md text-on-background">Data retention</h1>
		<span
			class="hidden text-[10px] font-bold uppercase tracking-widest text-on-surface-variant sm:inline"
			>/ Settings</span
		>
	</div>
	{#if $profile?.is_admin}<button
			type="button"
			class="btn-secondary flex items-center gap-2 px-3 py-2 text-xs font-bold disabled:opacity-40"
			onclick={load}
			disabled={busy || refreshing}
			>{#if refreshing}<Spinner class="text-base" />{:else}<span
					class="material-symbols-outlined text-[16px]"
					aria-hidden="true">refresh</span
				>{/if}Refresh</button
		>{/if}
</header>

<div class="space-y-6 px-container-padding pb-12 pt-24">
	{#if !$profile?.is_admin}
		<div class="settings-card flex flex-col items-center gap-3 px-6 py-12 text-center">
			<span class="material-symbols-outlined text-3xl text-on-surface-variant" aria-hidden="true"
				>lock</span
			>
			<h2 class="text-sm font-bold">Administrator access required</h2>
			<p class="text-sm text-on-surface-variant">
				Retention policies affect metric history across all servers and projects.
			</p>
		</div>
	{:else}
		{#if error}<div
				role="alert"
				class="flex flex-wrap items-center gap-3 rounded-lg border border-status-danger/30 bg-status-danger/5 px-4 py-3 text-sm text-status-danger"
			>
				<span class="material-symbols-outlined text-[18px]" aria-hidden="true">error</span>
				<p class="flex-1">{error}</p>
				<button
					type="button"
					class="text-xs font-bold underline underline-offset-4 disabled:opacity-40"
					onclick={load}
					disabled={busy || refreshing}>Reload policies</button
				>
			</div>{/if}
		{#if success}<div
				role="status"
				class="flex items-start gap-3 rounded-lg border border-status-healthy/30 bg-status-healthy/5 px-4 py-3 text-sm text-status-healthy"
			>
				<span class="material-symbols-outlined text-[18px]" aria-hidden="true">check_circle</span>
				<p>{success}</p>
			</div>{/if}
		{#if loading}
			<div
				class="settings-card flex items-center justify-center gap-3 py-20 text-sm text-on-surface-variant"
			>
				<Spinner class="text-xl text-primary" />Loading retention policies…
			</div>
		{:else if !policies.length && !error}
			<div class="settings-card flex flex-col items-center gap-3 px-6 py-16 text-center">
				<span class="material-symbols-outlined text-4xl text-on-surface-variant" aria-hidden="true"
					>database</span
				>
				<h2 class="text-sm font-bold">No metric hypertables available</h2>
				<p class="max-w-sm text-sm text-on-surface-variant">
					Metric tables will appear here when TimescaleDB is configured and metrics are collected.
				</p>
			</div>
		{:else if policy}
			<div class="flex flex-wrap items-start justify-between gap-4">
				<div>
					<h2 class="text-lg font-bold text-on-surface">Manage metric history</h2>
					<p class="mt-1 max-w-xl text-sm leading-relaxed text-on-surface-variant">
						Choose how long to keep collected metrics, review the storage impact, then apply your
						changes.
					</p>
				</div>
				<div class="flex flex-wrap items-center gap-3 text-xs text-on-surface-variant">
					<span class="flex items-center gap-1.5"
						><span class="material-symbols-outlined text-[16px]" aria-hidden="true">database</span
						>{policies.length} tables</span
					><span class="h-3 w-px bg-outline-variant" aria-hidden="true"></span><span
						>{configuredCount} with retention</span
					>{#if pausedCount}<span class="flex items-center gap-1 text-status-warning"
							><span class="material-symbols-outlined text-[15px]" aria-hidden="true"
								>pause_circle</span
							>{pausedCount} paused</span
						>{/if}
				</div>
			</div>
			<div class="grid items-start gap-5 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
				<form
					class="settings-card min-w-0 overflow-hidden"
					aria-labelledby="retention-policy-title"
					onsubmit={(event) => {
						event.preventDefault();
						void simulate();
					}}
				>
					<div class="flex items-center gap-2 border-b border-outline-variant px-5 py-4">
						<span
							class="material-symbols-outlined text-[18px] text-on-surface-variant"
							aria-hidden="true">tune</span
						>
						<h2 id="retention-policy-title" class="text-sm font-bold">Retention policy</h2>
					</div>
					<div class="space-y-6 p-5">
						<div class="space-y-2">
							<label for="retention-table" class="block text-xs font-bold text-on-surface-variant"
								>Metric table</label
							>
							{#if global}<div
									class="flex min-h-10 items-center justify-between gap-2 rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2 text-sm"
								>
									<span class="flex items-center gap-2"
										><span
											class="material-symbols-outlined text-[16px] text-primary"
											aria-hidden="true">stacks</span
										>All metric tables</span
									><span class="font-mono text-xs text-on-surface-variant"
										>{policies.length} tables</span
									>
								</div>{:else}<Select
									id="retention-table"
									class="w-full"
									aria-label="Metric table"
									options={policies.map((item) => ({
										value: item.name,
										label: `metric.${item.name}`
									}))}
									value={selected}
									onchange={select}
									disabled={busy || refreshing}
								/>{/if}
							{#if !global}<p class="text-xs text-on-surface-variant">
									Current retention <span class="ml-1 font-mono text-on-surface"
										>{policy.retention_interval ?? 'Not configured'}</span
									>
								</p>{/if}
						</div>
						<div>
							<label
								for="retention-amount"
								class="mb-2 block text-xs font-bold text-on-surface-variant">Keep data for</label
							>
							<div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3">
								<input
									id="retention-amount"
									aria-label="Retention amount"
									aria-describedby="retention-duration-hint"
									class="input-technical min-h-10 w-full min-w-0 px-3 py-2 font-mono text-sm tabular-nums"
									type="number"
									min="1"
									max="100000"
									step="1"
									required
									bind:value
									disabled={busy || refreshing}
								/><Select
									aria-label="Retention unit"
									options={retentionUnits.map((item) => ({
										value: item,
										label: item[0].toUpperCase() + item.slice(1)
									}))}
									value={unit}
									onchange={(next) => (unit = next as RetentionUnit)}
									disabled={busy || refreshing}
								/>
							</div>
							<p id="retention-duration-hint" class="mt-2 text-xs text-on-surface-variant">
								Data older than this period becomes eligible for cleanup. Months follow the
								calendar.
							</p>
						</div>
						<label
							class="flex cursor-pointer items-start justify-between gap-4 rounded-lg border border-outline-variant bg-surface-container-low p-4"
							><span
								><span class="block text-sm font-bold">Apply to all metric tables</span><span
									class="mt-1 block text-xs leading-relaxed text-on-surface-variant"
									>Replicate this period across all {policies.length} tables, including those without
									a policy.</span
								></span
							><input
								class="mt-1 shrink-0"
								type="checkbox"
								role="switch"
								bind:checked={global}
								disabled={busy || refreshing}
								onchange={changeScope}
							/></label
						>
						{#if global}<p class="flex gap-2 text-xs leading-relaxed text-on-surface-variant">
								<span class="material-symbols-outlined shrink-0 text-[16px]" aria-hidden="true"
									>info</span
								>Existing schedules and paused jobs are preserved. Future tables need a separate
								policy.
							</p>{:else if policy.job_id !== null && !policy.scheduled}<p
								class="flex gap-2 text-xs leading-relaxed text-status-warning"
							>
								<span class="material-symbols-outlined shrink-0 text-[16px]" aria-hidden="true"
									>pause_circle</span
								>This job is paused. Updating retention preserves its paused state.
							</p>{/if}
					</div>
					<div
						class="flex flex-wrap items-center justify-between gap-3 border-t border-outline-variant bg-surface-container-low px-5 py-4"
					>
						<span class="text-xs text-on-surface-variant">Preview changes before saving.</span
						><button
							class="btn-secondary flex items-center justify-center gap-2 px-4 py-2 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-40"
							type="submit"
							disabled={busy || refreshing || !valid}
							>{#if busy && !saving}<Spinner class="text-base" />{:else}<span
									class="material-symbols-outlined text-[16px]"
									aria-hidden="true">query_stats</span
								>{/if}{busy && !saving ? 'Estimating…' : 'Estimate impact'}</button
						>
					</div>
				</form>
				<RetentionImpact
					{preview}
					{fresh}
					busy={busy || refreshing}
					{saving}
					{global}
					count={policies.length}
					onsave={save}
				/>
			</div>
			<RetentionPolicies
				{policies}
				selected={global ? '' : selected}
				preview={fresh ? preview : null}
				disabled={busy || refreshing}
				onselect={editTable}
			/>
			<p class="flex items-start gap-2 text-xs leading-relaxed text-on-surface-variant">
				<span class="material-symbols-outlined shrink-0 text-[16px]" aria-hidden="true">info</span
				>Policies affect the PGWarden metrics database across all monitored servers and projects.
				Cleanup runs automatically when entire chunks expire.
			</p>
		{/if}
	{/if}
</div>
