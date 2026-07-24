<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		listNotifierRules,
		listNotifierRuleTypes,
		createNotifierRule,
		createNotifierThreshold,
		patchNotifierRule,
		patchNotifierThreshold,
		deleteNotifierThreshold,
		listServers,
		listDatabases,
		getDatabaseSchema,
		type NotifierRule,
		type NotifierThreshold
	} from '$lib/api';

	type Scope = NotifierThreshold['scope'];
	type RuleDraft = {
		interval_seconds: number;
		cooldown_seconds: number;
		window_minutes: number;
		enabled: boolean;
	};
	type ThresholdDraft = {
		warning: number;
		critical: number;
		direction: 'above' | 'below';
	};
	type EntityOption = { id: string; label: string };
	type CreateThresholdRow = {
		type: string;
		entity_public_id: string;
		warning: number;
		critical: number;
		direction: 'above' | 'below';
	};

	const validScopes: Scope[] = ['server', 'database', 'table', 'index'];
	const scopeMeta: Record<Scope, { title: string; icon: string; description: string }> = {
		server: {
			title: 'Server alerts',
			icon: 'dns',
			description: 'CPU, memory and disk usage rules evaluated per monitored server.'
		},
		database: {
			title: 'Database alerts',
			icon: 'database',
			description: 'Growth, cache hit ratio, deadlocks, sessions and schema change rules.'
		},
		table: {
			title: 'Table alerts',
			icon: 'table',
			description: 'Growth, dead tuples and column change rules evaluated per table.'
		},
		index: {
			title: 'Index alerts',
			icon: 'speed',
			description: 'Index hit rate rules evaluated per index.'
		}
	};

	const scope = $derived(($page.params.scope ?? '') as Scope);
	const meta = $derived(scopeMeta[scope]);

	let rules = $state<NotifierRule[]>([]);
	let ruleTypes = $state<string[]>([]);
	let entityOptions = $state<EntityOption[]>([]);
	let entityLabels = $state<Record<string, string>>({});
	let ruleDrafts = $state<Record<number, RuleDraft>>({});
	let thresholdDrafts = $state<Record<number, ThresholdDraft>>({});
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');

	let showCreate = $state(false);
	let createName = $state('');
	let createInterval = $state(60);
	let createCooldown = $state(1800);
	let createWindow = $state(5);
	let createRows = $state<CreateThresholdRow[]>([]);
	let creating = $state(false);
	let createError = $state('');

	const scopeRules = $derived(
		rules.filter((rule) => rule.thresholds.some((threshold) => threshold.scope === scope))
	);

	const changedRules = $derived(
		scopeRules.filter((rule) => {
			const draft = ruleDrafts[rule.id];
			if (!draft) return false;
			return (
				draft.interval_seconds !== rule.interval_seconds ||
				draft.cooldown_seconds !== rule.cooldown_seconds ||
				draft.window_minutes !== rule.window_minutes ||
				draft.enabled !== rule.enabled
			);
		})
	);

	const changedThresholds = $derived(
		scopeRules.flatMap((rule) =>
			rule.thresholds.filter((threshold) => {
				if (threshold.scope !== scope) return false;
				const draft = thresholdDrafts[threshold.id];
				if (!draft) return false;
				return (
					draft.warning !== threshold.warning ||
					draft.critical !== threshold.critical ||
					draft.direction !== threshold.direction
				);
			})
		)
	);

	const hasChanges = $derived(changedRules.length > 0 || changedThresholds.length > 0);

	function toRuleDraft(rule: NotifierRule): RuleDraft {
		return {
			interval_seconds: rule.interval_seconds,
			cooldown_seconds: rule.cooldown_seconds,
			window_minutes: rule.window_minutes,
			enabled: rule.enabled
		};
	}

	function toThresholdDraft(threshold: NotifierThreshold): ThresholdDraft {
		return {
			warning: threshold.warning,
			critical: threshold.critical,
			direction: threshold.direction
		};
	}

	async function load() {
		try {
			loading = true;
			error = '';
			const [rulesData, typesData] = await Promise.all([
				listNotifierRules(),
				listNotifierRuleTypes()
			]);
			rules = rulesData;
			ruleTypes = typesData[scope] ?? [];
			ruleDrafts = Object.fromEntries(rules.map((rule) => [rule.id, toRuleDraft(rule)]));
			thresholdDrafts = Object.fromEntries(
				rules.flatMap((rule) =>
					rule.thresholds.map((threshold) => [threshold.id, toThresholdDraft(threshold)])
				)
			);
			await loadEntities();
		} catch (err: any) {
			handleError(err, 'Failed to load alert rules.');
		} finally {
			loading = false;
		}
	}

	async function loadEntities() {
		const options: EntityOption[] = [];
		if (scope === 'server') {
			const servers = await listServers();
			options.push(...servers.map((server) => ({ id: server.id, label: server.name })));
		} else if (scope === 'database') {
			const databases = await listDatabases();
			options.push(...databases.map((db) => ({ id: db.id, label: db.name })));
		} else {
			const databases = await listDatabases();
			for (const db of databases) {
				const schema = await getDatabaseSchema(db.id);
				for (const table of schema.tables) {
					if (scope === 'table') {
						options.push({
							id: table.id,
							label: `${db.name} · ${table.schema_name}.${table.name}`
						});
					} else {
						for (const index of table.indexes) {
							options.push({
								id: index.id,
								label: `${db.name} · ${table.schema_name}.${table.name} / ${index.name}`
							});
						}
					}
				}
			}
		}
		entityOptions = options;
		entityLabels = Object.fromEntries(options.map((option) => [option.id, option.label]));
	}

	function updateRuleDraft(ruleId: number, patch: Partial<RuleDraft>) {
		const rule = rules.find((item) => item.id === ruleId);
		if (!rule) return;
		const current = ruleDrafts[ruleId] ?? toRuleDraft(rule);
		ruleDrafts = { ...ruleDrafts, [ruleId]: { ...current, ...patch } };
	}

	function updateThresholdDraft(threshold: NotifierThreshold, patch: Partial<ThresholdDraft>) {
		const current = thresholdDrafts[threshold.id] ?? toThresholdDraft(threshold);
		thresholdDrafts = { ...thresholdDrafts, [threshold.id]: { ...current, ...patch } };
	}

	async function saveChanges() {
		if (!hasChanges) return;

		try {
			saving = true;
			error = '';
			await Promise.all([
				...changedRules.map((rule) => patchNotifierRule(rule.id, ruleDrafts[rule.id])),
				...changedThresholds.map((threshold) =>
					patchNotifierThreshold(
						threshold.rule_id,
						threshold.scope,
						threshold.id,
						thresholdDrafts[threshold.id]
					)
				)
			]);
			await load();
		} catch (err: any) {
			handleError(err, 'Failed to update alert rules.');
		} finally {
			saving = false;
		}
	}

	async function removeThreshold(threshold: NotifierThreshold) {
		try {
			saving = true;
			error = '';
			await deleteNotifierThreshold(threshold.rule_id, threshold.scope, threshold.id);
			rules = rules.map((rule) =>
				rule.id === threshold.rule_id
					? { ...rule, thresholds: rule.thresholds.filter((item) => item.id !== threshold.id) }
					: rule
			);
		} catch (err: any) {
			handleError(err, 'Failed to delete threshold.');
		} finally {
			saving = false;
		}
	}

	function emptyRow(): CreateThresholdRow {
		return {
			type: ruleTypes[0] ?? '',
			entity_public_id: '',
			warning: 0,
			critical: 0,
			direction: 'above'
		};
	}

	function openCreate() {
		createName = '';
		createInterval = 60;
		createCooldown = 1800;
		createWindow = 5;
		createRows = [emptyRow()];
		createError = '';
		showCreate = true;
	}

	function addCreateRow() {
		createRows = [...createRows, emptyRow()];
	}

	function removeCreateRow(index: number) {
		createRows = createRows.filter((_, i) => i !== index);
	}

	function updateCreateRow(index: number, patch: Partial<CreateThresholdRow>) {
		createRows = createRows.map((row, i) => (i === index ? { ...row, ...patch } : row));
	}

	const createValid = $derived(
		createName.trim().length > 0 &&
			createRows.length > 0 &&
			createRows.every((row) => row.type.length > 0)
	);

	async function submitCreate() {
		if (!createValid || creating) return;

		try {
			creating = true;
			createError = '';
			const rule = await createNotifierRule({
				name: createName.trim(),
				interval_seconds: createInterval,
				cooldown_seconds: createCooldown,
				window_minutes: createWindow
			});
			for (const row of createRows) {
				await createNotifierThreshold(rule.id, {
					scope,
					type: row.type,
					entity_public_id: row.entity_public_id || null,
					warning: row.warning,
					critical: row.critical,
					direction: row.direction
				});
			}
			showCreate = false;
			await load();
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			createError = err.message || 'Failed to create rule.';
		} finally {
			creating = false;
		}
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

	function entityLabel(threshold: NotifierThreshold) {
		if (threshold.entity_public_id === null) return 'all entities';
		return entityLabels[threshold.entity_public_id] ?? `entity #${threshold.entity_id}`;
	}

	onMount(() => {
		if (!validScopes.includes(scope)) {
			goto('/alerts/server', { replaceState: true });
			return;
		}
		load();
	});
</script>

{#if validScopes.includes(scope)}
	<header
		class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
	>
		<span class="material-symbols-outlined text-on-surface-variant">notifications</span>
		<h1 class="font-headline-md text-headline-md text-on-background m-0">Alerts</h1>
		<span class="text-on-surface-variant">/</span>
		<span
			class="font-label-caps text-[10px] text-on-surface-variant uppercase tracking-widest"
			>{scope}</span
		>
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
						<span class="material-symbols-outlined text-on-surface-variant text-[18px]"
							>{meta.icon}</span
						>
						<h2 class="font-bold text-on-surface text-base m-0">{meta.title}</h2>
					</div>
					<p class="text-sm text-on-surface-variant">{meta.description}</p>
				</div>

				<div class="flex flex-wrap items-center gap-3">
					<button
						onclick={openCreate}
						disabled={saving || loading}
						class="flex items-center gap-2 px-4 py-2 rounded-lg border border-outline-variant text-on-surface text-sm font-bold transition-all active:scale-95 hover:bg-surface-variant disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
					>
						<span class="material-symbols-outlined text-[18px]">add</span>
						New rule
					</button>
					<button
						onclick={saveChanges}
						disabled={!hasChanges || saving || loading}
						class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold transition-all active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
					>
						<span class="material-symbols-outlined text-[18px]">save</span>
						{saving ? 'Updating...' : 'Update'}
					</button>
				</div>
			</div>
		</section>

		{#if loading}
			<div class="settings-card p-6 space-y-4">
				{#each [1, 2, 3] as _}
					<div class="skeleton h-16 w-full"></div>
				{/each}
			</div>
		{:else if scopeRules.length === 0}
			<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
				<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3"
					>notifications_off</span
				>
				<p class="text-on-surface font-bold mb-1">No {scope} alert rules found</p>
				<p class="text-sm text-on-surface-variant">
					Create a rule to start monitoring {scope} metrics.
				</p>
			</div>
		{:else}
			{#each scopeRules as rule (rule.id)}
				{@const draft = ruleDrafts[rule.id] ?? toRuleDraft(rule)}
				{@const scopedThresholds = rule.thresholds.filter(
					(threshold) => threshold.scope === scope
				)}
				<section class="settings-card overflow-hidden">
					<div class="row-item px-5 py-4 flex flex-wrap items-center justify-between gap-4">
						<div class="min-w-0">
							<p class="font-bold text-on-surface text-sm truncate">{formatName(rule.name)}</p>
							<p class="text-xs text-on-surface-variant">
								{scopedThresholds.length} threshold{scopedThresholds.length === 1 ? '' : 's'}
							</p>
						</div>

						<label class="flex items-center gap-2 text-xs font-bold text-on-surface">
							<input
								type="checkbox"
								checked={draft.enabled}
								disabled={saving}
								onchange={(event) =>
									updateRuleDraft(rule.id, { enabled: event.currentTarget.checked })}
								class="accent-primary"
							/>
							Active
						</label>
					</div>

					<div class="row-item px-5 py-4 flex flex-wrap items-center gap-x-8 gap-y-3">
						<div class="flex items-center gap-2">
							<label class="text-xs text-on-surface-variant" for={`interval-${rule.id}`}
								>Interval (s)</label
							>
							<input
								id={`interval-${rule.id}`}
								type="number"
								min="0"
								step="1"
								value={draft.interval_seconds}
								disabled={saving}
								oninput={(event) =>
									updateRuleDraft(rule.id, {
										interval_seconds: Number(event.currentTarget.value)
									})}
								class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
						</div>

						<div class="flex items-center gap-2">
							<label class="text-xs text-on-surface-variant" for={`cooldown-${rule.id}`}
								>Cooldown (s)</label
							>
							<input
								id={`cooldown-${rule.id}`}
								type="number"
								min="0"
								step="1"
								value={draft.cooldown_seconds}
								disabled={saving}
								oninput={(event) =>
									updateRuleDraft(rule.id, {
										cooldown_seconds: Number(event.currentTarget.value)
									})}
								class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
						</div>

						<div class="flex items-center gap-2">
							<label class="text-xs text-on-surface-variant" for={`window-${rule.id}`}
								>Window (min)</label
							>
							<input
								id={`window-${rule.id}`}
								type="number"
								min="0"
								step="1"
								value={draft.window_minutes}
								disabled={saving}
								oninput={(event) =>
									updateRuleDraft(rule.id, {
										window_minutes: Number(event.currentTarget.value)
									})}
								class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
						</div>
					</div>

					{#each scopedThresholds as threshold (threshold.id)}
						{@const thresholdDraft = thresholdDrafts[threshold.id] ?? toThresholdDraft(threshold)}
						<div class="row-item px-5 py-4 flex flex-wrap items-center justify-between gap-4">
							<div class="flex items-center gap-3 min-w-0">
								<span class="material-symbols-outlined text-on-surface-variant text-[18px]"
									>{meta.icon}</span
								>
								<div class="min-w-0">
									<p class="font-bold text-on-surface text-sm truncate">
										{formatName(threshold.type)}
									</p>
									<p class="text-xs text-on-surface-variant truncate">
										{entityLabel(threshold)}
									</p>
								</div>
							</div>

							<div class="flex flex-wrap items-center gap-4 flex-shrink-0">
								<div class="flex items-center gap-2">
									<label class="text-xs text-on-surface-variant" for={`warning-${threshold.id}`}
										>Warning</label
									>
									<input
										id={`warning-${threshold.id}`}
										type="number"
										step="0.1"
										value={thresholdDraft.warning}
										disabled={saving}
										oninput={(event) =>
											updateThresholdDraft(threshold, {
												warning: Number(event.currentTarget.value)
											})}
										class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
									/>
								</div>

								<div class="flex items-center gap-2">
									<label class="text-xs text-on-surface-variant" for={`critical-${threshold.id}`}
										>Critical</label
									>
									<input
										id={`critical-${threshold.id}`}
										type="number"
										step="0.1"
										value={thresholdDraft.critical}
										disabled={saving}
										oninput={(event) =>
											updateThresholdDraft(threshold, {
												critical: Number(event.currentTarget.value)
											})}
										class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
									/>
								</div>

								<select
									value={thresholdDraft.direction}
									disabled={saving}
									onchange={(event) =>
										updateThresholdDraft(threshold, {
											direction: event.currentTarget.value as 'above' | 'below'
										})}
									class="bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
								>
									<option value="above">Above</option>
									<option value="below">Below</option>
								</select>

								<button
									onclick={() => removeThreshold(threshold)}
									disabled={saving}
									title="Delete threshold"
									class="text-on-surface-variant hover:text-error transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
								>
									<span class="material-symbols-outlined text-[20px]">delete</span>
								</button>
							</div>
						</div>
					{:else}
						<div class="px-6 py-6 text-center text-sm text-on-surface-variant">
							No {scope} thresholds configured for this rule.
						</div>
					{/each}
				</section>
			{/each}
		{/if}
	</div>

	{#if showCreate}
		<div class="fixed inset-0 z-50 modal-overlay flex items-center justify-center p-4">
			<div class="settings-card w-full max-w-2xl p-8 shadow-floating max-h-[90vh] overflow-y-auto">
				<div class="flex items-start gap-4 mb-6">
					<div
						class="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center flex-shrink-0 mt-0.5"
					>
						<span class="material-symbols-outlined text-primary text-[20px]">add_alert</span>
					</div>
					<div>
						<h2 class="font-headline-md text-headline-md font-bold text-on-surface m-0">
							New {scope} rule
						</h2>
						<p class="text-[12px] text-on-surface-variant mt-1 leading-relaxed">
							Create a rule with one or more {scope} thresholds. Leave the entity as "All
							entities" to target the whole scope.
						</p>
					</div>
				</div>

				{#if createError}
					<div
						class="p-3 mb-4 bg-error-container/20 border-l-4 border-error rounded-r flex items-center gap-3"
					>
						<span class="material-symbols-outlined text-error text-[18px]">error</span>
						<p class="text-xs text-error">{createError}</p>
					</div>
				{/if}

				<div class="space-y-4">
					<div>
						<label class="text-xs text-on-surface-variant" for="create-name">Rule name</label>
						<input
							id="create-name"
							type="text"
							bind:value={createName}
							disabled={creating}
							placeholder="e.g. critical_tables"
							class="mt-1 w-full bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
						/>
					</div>

					<div class="flex flex-wrap gap-4">
						<div>
							<label class="text-xs text-on-surface-variant" for="create-interval"
								>Interval (s)</label
							>
							<input
								id="create-interval"
								type="number"
								min="0"
								step="1"
								bind:value={createInterval}
								disabled={creating}
								class="mt-1 w-28 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
						</div>
						<div>
							<label class="text-xs text-on-surface-variant" for="create-cooldown"
								>Cooldown (s)</label
							>
							<input
								id="create-cooldown"
								type="number"
								min="0"
								step="1"
								bind:value={createCooldown}
								disabled={creating}
								class="mt-1 w-28 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
						</div>
						<div>
							<label class="text-xs text-on-surface-variant" for="create-window"
								>Window (min)</label
							>
							<input
								id="create-window"
								type="number"
								min="0"
								step="1"
								bind:value={createWindow}
								disabled={creating}
								class="mt-1 w-28 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
							/>
						</div>
					</div>

					<div>
						<div class="flex items-center justify-between mb-2">
							<p class="text-xs font-bold text-on-surface m-0">Thresholds</p>
							<button
								onclick={addCreateRow}
								disabled={creating}
								class="flex items-center gap-1 text-xs text-primary font-bold hover:underline disabled:opacity-40"
							>
								<span class="material-symbols-outlined text-[16px]">add</span>
								Add threshold
							</button>
						</div>

						<div class="space-y-3">
							{#each createRows as row, index (index)}
								<div class="rounded-lg border border-outline-variant/50 p-3 space-y-3">
									<div class="flex items-center justify-between gap-3">
										<select
											value={row.type}
											disabled={creating}
											onchange={(event) =>
												updateCreateRow(index, { type: event.currentTarget.value })}
											class="flex-1 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
										>
											{#each ruleTypes as type}
												<option value={type}>{formatName(type)}</option>
											{/each}
										</select>
										<button
											onclick={() => removeCreateRow(index)}
											disabled={creating || createRows.length === 1}
											title="Remove threshold"
											class="text-on-surface-variant hover:text-error transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
										>
											<span class="material-symbols-outlined text-[18px]">close</span>
										</button>
									</div>

									<select
										value={row.entity_public_id}
										disabled={creating}
										onchange={(event) =>
											updateCreateRow(index, {
												entity_public_id: event.currentTarget.value
											})}
										class="w-full bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
									>
										<option value="">All entities</option>
										{#each entityOptions as option}
											<option value={option.id}>{option.label}</option>
										{/each}
									</select>

									<div class="flex flex-wrap items-center gap-3">
										<div class="flex items-center gap-2">
											<label class="text-xs text-on-surface-variant" for={`row-warning-${index}`}
												>Warning</label
											>
											<input
												id={`row-warning-${index}`}
												type="number"
												step="0.1"
												value={row.warning}
												disabled={creating}
												oninput={(event) =>
													updateCreateRow(index, {
														warning: Number(event.currentTarget.value)
													})}
												class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
											/>
										</div>
										<div class="flex items-center gap-2">
											<label class="text-xs text-on-surface-variant" for={`row-critical-${index}`}
												>Critical</label
											>
											<input
												id={`row-critical-${index}`}
												type="number"
												step="0.1"
												value={row.critical}
												disabled={creating}
												oninput={(event) =>
													updateCreateRow(index, {
														critical: Number(event.currentTarget.value)
													})}
												class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
											/>
										</div>
										<select
											value={row.direction}
											disabled={creating}
											onchange={(event) =>
												updateCreateRow(index, {
													direction: event.currentTarget.value as 'above' | 'below'
												})}
											class="bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
										>
											<option value="above">Above</option>
											<option value="below">Below</option>
										</select>
									</div>
								</div>
							{/each}
						</div>
					</div>
				</div>

				<div class="flex items-center justify-end gap-3 mt-6">
					<button
						onclick={() => (showCreate = false)}
						disabled={creating}
						class="px-4 py-2 rounded-lg border border-outline-variant text-on-surface-variant text-sm font-bold transition-all active:scale-95 hover:bg-surface-variant disabled:opacity-40"
					>
						Cancel
					</button>
					<button
						onclick={submitCreate}
						disabled={!createValid || creating}
						class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold transition-all active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
					>
						<span class="material-symbols-outlined text-[18px]">add</span>
						{creating ? 'Creating...' : 'Create rule'}
					</button>
				</div>
			</div>
		</div>
	{/if}
{/if}

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
	.modal-overlay {
		background: rgba(0, 0, 0, 0.65);
		backdrop-filter: blur(5px);
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
