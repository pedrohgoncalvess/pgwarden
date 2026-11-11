<script lang="ts">
	import { onMount } from 'svelte';
	import Select from '$lib/components/Select.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { formatBytes, retentionUnits, type RetentionUnit } from '$lib/retention-api';
	import {
		listScopeSettings,
		previewScope,
		saveScope,
		inheritScope,
		globalScopeId,
		type Scope,
		type ScopeSettings,
		type ScopedPreview
	} from '$lib/retention-scopes';
	let { onchange = () => {} }: { onchange?: () => void } = $props();
	let settings = $state<ScopeSettings | null>(null);
	let scope = $state<Scope>('server');
	let target = $state('');
	let table = $state('*');
	let value = $state<number | undefined>(30);
	let unit = $state<RetentionUnit>('days');
	let busy = $state(false);
	let error = $state('');
	let message = $state('');
	let preview = $state<ScopedPreview | null>(null);
	let previewKey = $state('');
	const key = $derived(`${scope}:${target}:${table}:${value}:${unit}`);
	const targets = $derived(
		scope === 'global'
			? [{ value: globalScopeId, label: 'All projects and servers' }]
			: scope === 'project'
				? (settings?.projects ?? []).map((item) => ({ value: item.id, label: item.name }))
				: (settings?.servers ?? [])
						.filter((item) => !item.deleted_at)
						.map((item) => ({ value: item.public_id, label: item.name }))
	);
	const explicit = $derived(
		settings?.policies.find(
			(item) => item.scope === scope && item.scope_id === target && item.table_name === table
		)
	);
	const valid = $derived(
		!!target && value !== undefined && Number.isInteger(value) && value > 0 && value <= 100000
	);
	const fresh = $derived(preview !== null && previewKey === key && valid);
	const effective = $derived(
		(settings?.effective ?? []).filter(
			(item) =>
				(table === '*' || item.name === table) &&
				(scope === 'global' ||
					(scope === 'server'
						? item.server_id === target
						: settings?.servers.some(
								(server) =>
									server.public_id === item.server_id && server.ingestion_project_id === target
							)))
		)
	);
	function reset() {
		preview = null;
		error = '';
		message = '';
	}
	function selectTarget(next: string) {
		target = next;
		reset();
		const current = settings?.policies.find(
			(item) => item.scope === scope && item.scope_id === target && item.table_name === table
		);
		if (current) {
			value = current.value;
			unit = current.unit;
		}
	}
	function selectScope(next: string) {
		scope = next as Scope;
		selectTarget(
			scope === 'global'
				? globalScopeId
				: scope === 'project'
					? (settings?.projects[0]?.id ?? '')
					: (settings?.servers.find((item) => !item.deleted_at)?.public_id ?? '')
		);
	}
	async function load() {
		busy = true;
		error = '';
		try {
			settings = await listScopeSettings();
			selectScope(scope);
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not load scoped policies.';
		} finally {
			busy = false;
		}
	}
	async function estimate() {
		if (!valid || value === undefined) return;
		busy = true;
		error = '';
		message = '';
		preview = null;
		const requestedKey = key;
		try {
			preview = await previewScope(scope, target, table, { value, unit });
			previewKey = requestedKey;
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not estimate retention.';
		} finally {
			busy = false;
		}
	}
	async function save() {
		if (!fresh || value === undefined) return;
		busy = true;
		error = '';
		try {
			settings = await saveScope(scope, target, table, { value, unit });
			preview = null;
			message =
				'Scoped retention saved. Cleanup applies the effective rule for each server every minute.';
			onchange();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not save scoped retention.';
		} finally {
			busy = false;
		}
	}
	async function inherit() {
		busy = true;
		error = '';
		try {
			await inheritScope(scope, target, table);
			settings = await listScopeSettings();
			preview = null;
			message = 'Override removed. The inherited policy is now effective.';
			onchange();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not restore inheritance.';
		} finally {
			busy = false;
		}
	}
	onMount(() => {
		void load();
	});
</script>

<section class="settings-card min-w-0 overflow-hidden" aria-labelledby="scope-retention-title">
	<div class="border-b border-outline-variant px-5 py-4">
		<h2 id="scope-retention-title" class="text-sm font-bold">Project and server retention</h2>
		<p class="mt-1 text-xs text-on-surface-variant">
			Server overrides project; project overrides the global default. Table rules override all-table
			rules within the same scope.
		</p>
	</div>
	<div class="space-y-5 p-5">
		{#if error}<p role="alert" class="text-sm text-status-danger">
				{error} <button class="underline" onclick={load} disabled={busy}>Retry</button>
			</p>{/if}
		{#if message}<p role="status" class="text-sm text-status-healthy">{message}</p>{/if}
		{#if settings}
			<form
				class="space-y-4"
				onsubmit={(event) => {
					event.preventDefault();
					void estimate();
				}}
			>
				<div class="grid gap-4 md:grid-cols-3">
					<div>
						<p class="mb-2 text-xs font-bold text-on-surface-variant">Policy scope</p>
						<Select
							aria-label="Policy scope"
							options={[
								{ value: 'server', label: 'Server' },
								{ value: 'project', label: 'Project' },
								{ value: 'global', label: 'Global default' }
							]}
							value={scope}
							onchange={selectScope}
							disabled={busy}
							class="w-full"
						/>
					</div>
					<div>
						<p class="mb-2 text-xs font-bold text-on-surface-variant">Apply to</p>
						<Select
							aria-label="Retention target"
							options={targets}
							value={target}
							onchange={selectTarget}
							disabled={busy || !targets.length}
							placeholder="No targets available"
							class="w-full"
						/>
					</div>
					<div>
						<p class="mb-2 text-xs font-bold text-on-surface-variant">Metric table</p>
						<Select
							aria-label="Scoped metric table"
							options={[
								{ value: '*', label: 'All tables (inherited default)' },
								...settings.tables.map((name) => ({ value: name, label: `metric.${name}` }))
							]}
							value={table}
							onchange={(next) => {
								table = next;
								selectTarget(target);
							}}
							disabled={busy}
							class="w-full"
						/>
					</div>
				</div>
				<div class="flex flex-wrap items-end gap-3">
					<label class="block"
						><span class="mb-2 block text-xs font-bold text-on-surface-variant">Keep data for</span
						><input
							aria-label="Scoped retention amount"
							class="input-technical w-32 px-3 py-2 text-sm"
							type="number"
							min="1"
							max="100000"
							step="1"
							required
							bind:value
							disabled={busy}
						/></label
					>
					<div class="w-40">
						<Select
							aria-label="Scoped retention unit"
							options={retentionUnits.map((item) => ({ value: item, label: item }))}
							value={unit}
							onchange={(next) => (unit = next as RetentionUnit)}
							disabled={busy}
							class="w-full"
						/>
					</div>
					<button
						class="btn-secondary px-4 py-2 text-sm font-bold disabled:opacity-40"
						disabled={busy || !valid}
						type="submit">{busy ? 'Working…' : 'Estimate scoped impact'}</button
					><button
						class="btn-primary px-4 py-2 text-sm font-bold disabled:opacity-40"
						onclick={save}
						type="button"
						disabled={busy || !fresh}>Save scoped retention</button
					>{#if scope !== 'global' && explicit}<button
							class="btn-secondary px-4 py-2 text-sm disabled:opacity-40"
							type="button"
							onclick={inherit}
							disabled={busy}>Use inherited policy</button
						>{/if}
				</div>
				<p class="text-xs text-on-surface-variant">
					{explicit
						? `Explicit rule: ${explicit.retention_interval}${explicit.enabled ? '' : ' (paused)'}.`
						: 'No explicit rule at this level. Retention is inherited.'} More specific overrides are preserved
					when changing a default.
				</p>
			</form>
			{#if preview && fresh}<div
					class="space-y-3 rounded-lg border border-outline-variant bg-surface-container-low p-4"
					aria-live="polite"
				>
					<h3 class="text-sm font-bold">Scoped storage estimate</h3>
					<div class="grid gap-4 sm:grid-cols-3">
						{#each [['Logical data volume', formatBytes(preview.logical_bytes)], ['Projected logical volume', formatBytes(preview.projected_bytes)], ['Expired logical data', formatBytes(preview.expired_bytes)]] as [label, amount]}<div
							>
								<p class="text-xs text-on-surface-variant">{label}</p>
								<p class="mt-1 font-mono text-lg">{amount}</p>
							</div>{/each}
					</div>
					<p class="text-xs text-status-warning">
						{preview.expired_rows} rows are eligible for deletion across {preview.affected_tables} server/table
						combinations. Removed history cannot be restored.
					</p>
					<p class="text-xs leading-relaxed text-on-surface-variant">
						These are estimates of row data, excluding indexes, compression and free pages. Deletion
						makes space reusable; it does not guarantee immediate filesystem shrinkage. Projections
						assume the observed collection rate continues.
					</p>
					<p class="text-xs text-on-surface-variant">
						{preview.tables.filter((item) => item.preserved).length} more specific rules remain unchanged.
					</p>
				</div>{:else if preview}<p role="status" class="text-xs text-status-warning">
					Selection changed. Estimate again before saving.
				</p>{/if}
			<details class="border-t border-outline-variant pt-4">
				<summary class="cursor-pointer text-sm font-bold"
					>Effective policies and cleanup history ({effective.length})</summary
				>
				<div class="mt-4 overflow-x-auto">
					<table class="w-full whitespace-nowrap text-left text-xs">
						<thead
							><tr
								><th class="px-3 py-2">Server</th><th class="px-3 py-2">Table</th><th
									class="px-3 py-2">Effective retention</th
								><th class="px-3 py-2">Inherited from</th><th class="px-3 py-2">Last cleanup</th><th
									class="px-3 py-2">Rows removed</th
								></tr
							></thead
						><tbody
							>{#each effective as item (`${item.server_id}:${item.name}`)}{@const run =
									settings.runs.find(
										(run) => run.public_id === item.server_id && run.table_name === item.name
									)}<tr class="border-t border-outline-variant"
									><td class="px-3 py-2"
										>{settings.servers.find((server) => server.public_id === item.server_id)
											?.name}</td
									><td class="px-3 py-2 font-mono">{item.name}</td><td class="px-3 py-2"
										>{item.policy?.retention_interval ?? 'No retention limit'}{item.policy
											?.enabled === false
											? ' (paused)'
											: ''}</td
									><td class="px-3 py-2"
										>{item.policy?.scope ?? 'None'}{item.policy?.table_name === '*'
											? ' · all tables'
											: ' · table rule'}</td
									><td class="px-3 py-2"
										>{run ? new Date(run.last_run_at).toLocaleString() : 'Not run yet'}</td
									><td class="px-3 py-2 font-mono">{run?.deleted_rows ?? '—'}</td></tr
								>{/each}</tbody
						>
					</table>
				</div>
			</details>
		{:else if busy}<div class="flex items-center gap-2 text-sm text-on-surface-variant">
				<Spinner />Loading scoped policies…
			</div>{/if}
	</div>
</section>
