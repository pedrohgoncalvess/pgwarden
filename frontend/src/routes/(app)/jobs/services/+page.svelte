<script lang="ts">
	import { profile, can } from '$lib/access';
	import Spinner from '$lib/components/Spinner.svelte';
	import { onMount } from 'svelte';
	import {
		getServiceHealth,
		listAnalyticsServiceConfigs,
		listNotifierRules,
		patchAnalyticsServiceConfig,
		patchNotifierRule
	} from '$lib/api';
	import type { AnalyticsServiceConfig, HealthResponse, NotifierRule } from '$lib/api';

	let health = $state<HealthResponse | null>(null);
	let analyticsConfigs = $state<AnalyticsServiceConfig[]>([]);
	let notifierRules = $state<NotifierRule[]>([]);
	let analyticsDrafts = $state<Record<number, AnalyticsServiceConfig>>({});
	let notifierDrafts = $state<Record<number, { interval_seconds: number; enabled: boolean }>>({});
	let loading = $state(true);
	let saving = $state<string | null>(null);
	let error = $state('');

	function serviceLabel(status: 'healthy' | 'unavailable' | undefined): string {
		return status === 'healthy' ? 'Running' : 'Unavailable';
	}

	function serviceClass(status: 'healthy' | 'unavailable' | undefined): string {
		return status === 'healthy'
			? 'border-primary/30 bg-primary/10 text-primary'
			: 'border-error/30 bg-error/10 text-error';
	}

	async function load() {
		try {
			loading = true;
			error = '';
			const [nextHealth, configs, rules] = await Promise.all([
				getServiceHealth(),
				listAnalyticsServiceConfigs(),
				can($profile, 'alerts.read') ? listNotifierRules() : Promise.resolve([])
			]);
			health = nextHealth;
			analyticsConfigs = configs;
			notifierRules = rules;
			analyticsDrafts = Object.fromEntries(configs.map((config) => [config.id, { ...config }]));
			notifierDrafts = Object.fromEntries(
				rules.map((rule) => [
					rule.id,
					{ interval_seconds: rule.interval_seconds, enabled: rule.enabled }
				])
			);
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load service settings.';
		} finally {
			loading = false;
		}
	}

	function updateAnalytics(
		configId: number,
		field: keyof AnalyticsServiceConfig,
		value: number | boolean
	) {
		const current = analyticsDrafts[configId];
		if (!current) return;
		analyticsDrafts = { ...analyticsDrafts, [configId]: { ...current, [field]: value } };
	}

	function updateNotifier(
		ruleId: number,
		field: 'interval_seconds' | 'enabled',
		value: number | boolean
	) {
		const current = notifierDrafts[ruleId];
		if (!current) return;
		notifierDrafts = { ...notifierDrafts, [ruleId]: { ...current, [field]: value } };
	}

	function analyticsChanged(config: AnalyticsServiceConfig): boolean {
		const draft = analyticsDrafts[config.id];
		return Boolean(
			draft &&
			(draft.run_interval !== config.run_interval ||
				draft.query_analytics_enabled !== config.query_analytics_enabled ||
				draft.recommendation_enabled !== config.recommendation_enabled)
		);
	}

	function notifierChanged(rule: NotifierRule): boolean {
		const draft = notifierDrafts[rule.id];
		return Boolean(
			draft && (draft.interval_seconds !== rule.interval_seconds || draft.enabled !== rule.enabled)
		);
	}

	async function saveAnalytics(config: AnalyticsServiceConfig) {
		if (!can($profile, 'schedulers.configure')) return;
		const draft = analyticsDrafts[config.id];
		if (!draft || !analyticsChanged(config)) return;
		try {
			saving = `analytics-${config.id}`;
			const updated = await patchAnalyticsServiceConfig(config.id, {
				run_interval: Math.max(10, Math.round(draft.run_interval)),
				query_analytics_enabled: draft.query_analytics_enabled,
				recommendation_enabled: draft.recommendation_enabled
			});
			analyticsConfigs = analyticsConfigs.map((item) => (item.id === updated.id ? updated : item));
			analyticsDrafts = { ...analyticsDrafts, [updated.id]: { ...updated } };
		} catch (err: any) {
			error = err.message || 'Failed to update Analytics settings.';
		} finally {
			saving = null;
		}
	}

	async function saveNotifier(rule: NotifierRule) {
		if (!can($profile, 'alerts.configure')) return;
		const draft = notifierDrafts[rule.id];
		if (!draft || !notifierChanged(rule)) return;
		try {
			saving = `notifier-${rule.id}`;
			const updated = await patchNotifierRule(rule.id, draft);
			notifierRules = notifierRules.map((item) => (item.id === updated.id ? updated : item));
			notifierDrafts = {
				...notifierDrafts,
				[updated.id]: { interval_seconds: updated.interval_seconds, enabled: updated.enabled }
			};
		} catch (err: any) {
			error = err.message || 'Failed to update Notifier settings.';
		} finally {
			saving = null;
		}
	}

	onMount(() => load());
</script>

<header
	class="fixed top-0 right-0 z-40 flex h-16 app-page-header items-center justify-between border-b border-outline-variant bg-surface-dim px-container-padding"
>
	<div class="flex items-center gap-3">
		<span class="material-symbols-outlined text-primary">hub</span>
		<h1 class="m-0 font-headline-md text-headline-md text-on-background">Services</h1>
		<span class="text-[10px] font-label-caps text-on-surface-variant">/ RUN SETTINGS</span>
	</div>
	<button
		onclick={load}
		class="flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container px-4 py-2 text-sm font-bold text-on-surface hover:border-primary/40 hover:text-primary"
		><span class="material-symbols-outlined text-sm">refresh</span>Refresh</button
	>
</header>

<div class="space-y-6 px-container-padding pb-12 pt-24">
	{#if error}<div
			class="rounded-lg border border-error/30 bg-error-container/10 p-4 text-sm text-error"
		>
			{error}
		</div>{/if}
	<div class="grid gap-4 md:grid-cols-2">
		<div class="rounded-xl border p-4 {serviceClass(health?.services.analytics.status)}">
			<p class="m-0 text-xs uppercase tracking-wider">Analytics service</p>
			<p class="mt-2 text-lg font-bold">{serviceLabel(health?.services.analytics.status)}</p>
		</div>
		<div class="rounded-xl border p-4 {serviceClass(health?.services.notifier.status)}">
			<p class="m-0 text-xs uppercase tracking-wider">Notifier service</p>
			<p class="mt-2 text-lg font-bold">{serviceLabel(health?.services.notifier.status)}</p>
		</div>
	</div>

	{#if loading}<div class="flex justify-center py-16">
			<Spinner class="text-3xl text-primary" />
		</div>{:else}
		<section class="overflow-hidden rounded-xl border border-outline-variant bg-surface-container">
			<div class="border-b border-outline-variant px-5 py-4">
				<h2 class="m-0 font-bold text-on-surface">Analytics</h2>
				<p class="mb-0 mt-1 text-sm text-on-surface-variant">
					Schedule query parsing and recommendations for each monitored database.
				</p>
			</div>
			{#each analyticsConfigs as config}
				{@const draft = analyticsDrafts[config.id] ?? config}
				<div
					class="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant px-5 py-4 last:border-0"
				>
					<div>
						<p class="m-0 font-bold text-on-surface">{config.database_name}</p>
						<p class="mb-0 mt-1 text-xs text-on-surface-variant">
							Last synchronized: {config.last_seen
								? new Date(config.last_seen).toLocaleString()
								: 'Never'}
						</p>
					</div>
					<div class="flex flex-wrap items-center gap-4">
						<label class="text-xs text-on-surface-variant"
							>Interval (seconds)<input
								type="number"
								min="10"
								value={draft.run_interval}
								oninput={(event) =>
									updateAnalytics(config.id, 'run_interval', Number(event.currentTarget.value))}
								class="ml-2 w-20 rounded border border-outline-variant bg-surface-container-high px-2 py-1 text-on-surface"
							/></label
						><label class="flex items-center gap-2 text-xs text-on-surface"
							><input
								type="checkbox" role="switch"
								checked={draft.query_analytics_enabled}
								onchange={(event) =>
									updateAnalytics(
										config.id,
										'query_analytics_enabled',
										event.currentTarget.checked
									)}

							/>Query parsing</label
						><label class="flex items-center gap-2 text-xs text-on-surface"
							><input
								type="checkbox" role="switch"
								checked={draft.recommendation_enabled}
								onchange={(event) =>
									updateAnalytics(config.id, 'recommendation_enabled', event.currentTarget.checked)}

							/>Recommendations</label
						><button
							onclick={() => saveAnalytics(config)}
							disabled={!can($profile, 'schedulers.configure') || !analyticsChanged(config) || saving !== null}
							class="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-on-primary disabled:cursor-not-allowed disabled:opacity-40"
							>Save</button
						>
					</div>
				</div>{:else}<div class="p-8 text-center text-sm text-on-surface-variant">
					Analytics has not created database configurations yet.
				</div>{/each}
		</section>

		<section class="overflow-hidden rounded-xl border border-outline-variant bg-surface-container">
			<div class="border-b border-outline-variant px-5 py-4">
				<h2 class="m-0 font-bold text-on-surface">Notifier</h2>
				<p class="mb-0 mt-1 text-sm text-on-surface-variant">
					Manage alert rule scheduling. Notification channels remain in Alerts → Configuration.
				</p>
			</div>
			{#each notifierRules as rule}
				{@const draft = notifierDrafts[rule.id] ?? {
					interval_seconds: rule.interval_seconds,
					enabled: rule.enabled
				}}
				<div
					class="flex flex-wrap items-center justify-between gap-4 border-b border-outline-variant px-5 py-4 last:border-0"
				>
					<div>
						<p class="m-0 font-bold text-on-surface">{rule.name}</p>
						<p class="mb-0 mt-1 text-xs text-on-surface-variant">
							{rule.thresholds.length} thresholds · {rule.cooldown_seconds}s cooldown
						</p>
					</div>
					<div class="flex items-center gap-4">
						<label class="text-xs text-on-surface-variant"
							>Interval (seconds)<input
								type="number"
								min="1"
								value={draft.interval_seconds}
								oninput={(event) =>
									updateNotifier(rule.id, 'interval_seconds', Number(event.currentTarget.value))}
								class="ml-2 w-20 rounded border border-outline-variant bg-surface-container-high px-2 py-1 text-on-surface"
							/></label
						><label class="flex items-center gap-2 text-xs text-on-surface"
							><input
								type="checkbox" role="switch"
								checked={draft.enabled}
								onchange={(event) =>
									updateNotifier(rule.id, 'enabled', event.currentTarget.checked)}

							/>Active</label
						><button
							onclick={() => saveNotifier(rule)}
							disabled={!can($profile, 'alerts.configure') || !notifierChanged(rule) || saving !== null}
							class="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-on-primary disabled:cursor-not-allowed disabled:opacity-40"
							>Save</button
						>
					</div>
				</div>{:else}<div class="p-8 text-center text-sm text-on-surface-variant">
					No notifier rules configured.
				</div>{/each}
		</section>
	{/if}
</div>
