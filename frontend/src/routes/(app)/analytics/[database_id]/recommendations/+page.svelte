<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { getAnalyticsRecommendations, patchAnalyticsRecommendation } from '$lib/api';
	import type { AnalyticsRecommendation, AnalyticsRecommendationStatus } from '$lib/api';
	import RecommendationCard from './RecommendationCard.svelte';

	let items = $state<AnalyticsRecommendation[]>([]);
	let loading = $state(true);
	let error = $state('');
	let status = $state<AnalyticsRecommendationStatus | 'all'>('open');
	let updating = $state<Set<number>>(new Set());
	let expandedEvidenceId = $state<number | null>(null);

	const databaseId = $derived($page.params.database_id ?? '');
	const counts = $derived({
		total: items.length,
		critical: items.filter((item) => item.severity === 'critical').length,
		warning: items.filter((item) => item.severity === 'warning').length,
		info: items.filter((item) => item.severity === 'info').length
	});
	const statuses: { value: AnalyticsRecommendationStatus | 'all'; label: string }[] = [
		{ value: 'open', label: 'Open' },
		{ value: 'dismissed', label: 'Dismissed' },
		{ value: 'resolved', label: 'Resolved' },
		{ value: 'all', label: 'All' }
	];

	async function load() {
		if (!databaseId) return;
		loading = true;
		error = '';
		try {
			items = await getAnalyticsRecommendations(databaseId, status);
		} catch (loadError) {
			error = loadError instanceof Error ? loadError.message : 'Failed to load recommendations.';
		} finally {
			loading = false;
		}
	}

	async function update(item: AnalyticsRecommendation, nextStatus: AnalyticsRecommendationStatus) {
		if (!databaseId) return;
		updating = new Set([...updating, item.id]);
		error = '';
		try {
			const updated = await patchAnalyticsRecommendation(databaseId, item.id, nextStatus);
			items = items.map((entry) => (entry.id === updated.id ? updated : entry));
			if (status !== 'all' && status !== nextStatus) {
				items = items.filter((entry) => entry.id !== item.id);
			}
		} catch (updateError) {
			error =
				updateError instanceof Error ? updateError.message : 'Failed to update recommendation.';
		} finally {
			const next = new Set(updating);
			next.delete(item.id);
			updating = next;
		}
	}

	function selectStatus(nextStatus: AnalyticsRecommendationStatus | 'all') {
		if (status === nextStatus) return;
		status = nextStatus;
		void load();
	}

	function toggleEvidence(itemId: number, isOpen: boolean) {
		expandedEvidenceId = isOpen ? itemId : null;
	}

	onMount(() => void load());
</script>

<div class="min-w-0 px-container-padding pb-12 pt-24">
	<div class="mb-6 grid gap-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
		<div class="min-w-0">
			<p class="font-label-caps text-[10px] uppercase tracking-widest text-primary">Analytics</p>
			<h1 class="m-0 font-headline-lg text-headline-lg">Recommendations</h1>
			<p class="mt-2 max-w-3xl text-sm text-on-surface-variant">
				Actionable findings from query, schema, index, maintenance, and capacity data.
			</p>
		</div>
		<div
			class="flex max-w-full items-center gap-2 overflow-x-auto rounded-xl border border-outline-variant bg-surface-container p-1"
		>
			{#each statuses as option}
				<button
					onclick={() => selectStatus(option.value)}
					class="shrink-0 rounded-lg px-3 py-2 text-xs font-bold transition {status === option.value
						? 'bg-primary text-on-primary shadow-sm'
						: 'text-on-surface-variant hover:bg-surface-container-highest'}"
				>
					{option.label}
				</button>
			{/each}
			<button
				onclick={load}
				disabled={loading}
				class="ml-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-on-surface-variant hover:bg-surface-container-highest disabled:opacity-50"
				aria-label="Refresh recommendations"
				title="Refresh recommendations"
			>
				<span class="material-symbols-outlined text-[18px] {loading ? 'animate-spin' : ''}">
					refresh
				</span>
			</button>
		</div>
	</div>

	{#if error}
		<div
			class="mb-5 rounded-lg border border-error/30 bg-error-container/10 p-4 text-sm text-error"
		>
			{error}
		</div>
	{/if}

	<div class="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
		<div class="rounded-xl border border-outline-variant bg-surface-container p-4">
			<div class="text-2xl font-bold text-on-surface">{counts.total}</div>
			<div class="mt-1 text-xs font-bold uppercase tracking-wide text-on-surface-variant">
				Displayed
			</div>
		</div>
		<div class="rounded-xl border border-error/25 bg-error/5 p-4">
			<div class="text-2xl font-bold text-error">{counts.critical}</div>
			<div class="mt-1 text-xs font-bold uppercase tracking-wide text-error">Critical</div>
		</div>
		<div class="rounded-xl border border-tertiary/25 bg-tertiary/5 p-4">
			<div class="text-2xl font-bold text-tertiary">{counts.warning}</div>
			<div class="mt-1 text-xs font-bold uppercase tracking-wide text-tertiary">Warning</div>
		</div>
		<div class="rounded-xl border border-primary/20 bg-primary/5 p-4">
			<div class="text-2xl font-bold text-primary">{counts.info}</div>
			<div class="mt-1 text-xs font-bold uppercase tracking-wide text-primary">Information</div>
		</div>
	</div>

	{#if loading}
		<div class="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
			{#each [1, 2, 3] as placeholder}
				<div
					class="h-72 animate-pulse rounded-xl border border-outline-variant bg-surface-container"
					aria-hidden="true"
				>
					<div class="h-1 rounded-t-xl bg-primary/20"></div>
					<div class="space-y-4 p-5">
						<div class="h-9 w-3/4 rounded bg-surface-container-highest"></div>
						<div class="h-4 w-full rounded bg-surface-container-highest"></div>
						<div class="h-20 rounded bg-surface-container-highest"></div>
					</div>
				</div>
			{/each}
		</div>
	{:else if items.length === 0}
		<div
			class="rounded-xl border border-dashed border-outline-variant bg-surface-container p-10 text-center"
		>
			<span class="material-symbols-outlined text-4xl text-primary">tips_and_updates</span>
			<h2 class="mt-3 font-headline-md">
				No {status === 'all' ? '' : status} recommendations
			</h2>
			<p class="text-sm text-on-surface-variant">
				Run Analytics after enough metric data has been collected to generate findings.
			</p>
		</div>
	{:else}
		<div class="grid items-stretch gap-4 lg:grid-cols-2 2xl:grid-cols-3">
			{#each items as item (item.id)}
				<RecommendationCard
					{item}
					busy={updating.has(item.id)}
					{databaseId}
					onUpdate={(nextStatus) => update(item, nextStatus)}
					evidenceOpen={expandedEvidenceId === item.id}
					onEvidenceToggle={(isOpen) => toggleEvidence(item.id, isOpen)}
				/>
			{/each}
		</div>
	{/if}
</div>
