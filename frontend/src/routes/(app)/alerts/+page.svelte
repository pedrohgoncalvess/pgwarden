<script lang="ts">
	import { onMount } from 'svelte';
	import {
		listNotifierRules,
		patchNotifierRule,
		patchNotifierThreshold,
		deleteNotifierThreshold,
		type NotifierRule,
		type NotifierThreshold
	} from '$lib/api';

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

	const scopeIcons: Record<NotifierThreshold['scope'], string> = {
		server: 'dns',
		database: 'database',
		table: 'table',
		index: 'speed'
	};

	let rules = $state<NotifierRule[]>([]);
	let ruleDrafts = $state<Record<number, RuleDraft>>({});
	let thresholdDrafts = $state<Record<number, ThresholdDraft>>({});
	let loading = $state(true);
	let saving = $state(false);
	let error = $state('');

	const changedRules = $derived(
		rules.filter((rule) => {
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
		rules.flatMap((rule) =>
			rule.thresholds.filter((threshold) => {
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
			rules = await listNotifierRules();
			ruleDrafts = Object.fromEntries(rules.map((rule) => [rule.id, toRuleDraft(rule)]));
			thresholdDrafts = Object.fromEntries(
				rules.flatMap((rule) =>
					rule.thresholds.map((threshold) => [threshold.id, toThresholdDraft(threshold)])
				)
			);
		} catch (err: any) {
			handleError(err, 'Failed to load alert rules.');
		} finally {
			loading = false;
		}
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
				...changedRules.map((rule) =>
					patchNotifierRule(rule.id, ruleDrafts[rule.id])
				),
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
	<span class="material-symbols-outlined text-on-surface-variant">notifications</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">Alerts</h1>
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
					<span class="material-symbols-outlined text-on-surface-variant text-[18px]">tune</span>
					<h2 class="font-bold text-on-surface text-base m-0">Alert rules</h2>
				</div>
				<p class="text-sm text-on-surface-variant">
					Configure evaluation settings and thresholds for each alert rule.
				</p>
			</div>

			<button
				onclick={saveChanges}
				disabled={!hasChanges || saving || loading}
				class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-on-primary text-sm font-bold transition-all active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
			>
				<span class="material-symbols-outlined text-[18px]">save</span>
				{saving ? 'Updating...' : 'Update'}
			</button>
		</div>
	</section>

	{#if loading}
		<div class="settings-card p-6 space-y-4">
			{#each [1, 2, 3] as _}
				<div class="skeleton h-16 w-full"></div>
			{/each}
		</div>
	{:else if rules.length === 0}
		<div class="settings-card px-6 py-12 flex flex-col items-center text-center">
			<span class="material-symbols-outlined text-[40px] text-on-surface-variant mb-3"
				>notifications_off</span
			>
			<p class="text-on-surface font-bold mb-1">No alert rules found</p>
			<p class="text-sm text-on-surface-variant">
				Alert rules are synced from the notifier configuration.
			</p>
		</div>
	{:else}
		{#each rules as rule (rule.id)}
			{@const draft = ruleDrafts[rule.id] ?? toRuleDraft(rule)}
			<section class="settings-card overflow-hidden">
				<div class="row-item px-5 py-4 flex flex-wrap items-center justify-between gap-4">
					<div class="min-w-0">
						<p class="font-bold text-on-surface text-sm truncate">{formatName(rule.name)}</p>
						<p class="text-xs text-on-surface-variant">
							{rule.thresholds.length} threshold{rule.thresholds.length === 1 ? '' : 's'}
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
								updateRuleDraft(rule.id, { interval_seconds: Number(event.currentTarget.value) })}
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
								updateRuleDraft(rule.id, { cooldown_seconds: Number(event.currentTarget.value) })}
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
								updateRuleDraft(rule.id, { window_minutes: Number(event.currentTarget.value) })}
							class="w-24 bg-surface-container border border-outline-variant rounded-lg px-3 py-2 text-on-surface outline-none focus:border-primary"
						/>
					</div>
				</div>

				{#each rule.thresholds as threshold (threshold.id)}
					{@const thresholdDraft = thresholdDrafts[threshold.id] ?? toThresholdDraft(threshold)}
					<div class="row-item px-5 py-4 flex flex-wrap items-center justify-between gap-4">
						<div class="flex items-center gap-3 min-w-0">
							<span
								class="material-symbols-outlined text-on-surface-variant text-[18px]"
								title={threshold.scope}>{scopeIcons[threshold.scope]}</span
							>
							<div class="min-w-0">
								<p class="font-bold text-on-surface text-sm truncate">
									{formatName(threshold.type)}
								</p>
								<p class="text-xs text-on-surface-variant">
									{threshold.scope} · {threshold.entity_id === null
										? 'all entities'
										: `entity #${threshold.entity_id}`}
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
						No thresholds configured for this rule.
					</div>
				{/each}
			</section>
		{/each}
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
