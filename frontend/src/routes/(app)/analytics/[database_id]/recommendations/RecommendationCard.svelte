<script lang="ts">
	import { formatBytes } from '$lib/api';
	import type { AnalyticsRecommendation, AnalyticsRecommendationStatus } from '$lib/api';

	let {
		item,
		busy,
		databaseId,
		onUpdate,
		evidenceOpen,
		onEvidenceToggle
	}: {
		item: AnalyticsRecommendation;
		busy: boolean;
		databaseId: string;
		onUpdate: (status: AnalyticsRecommendationStatus) => void;
		evidenceOpen: boolean;
		onEvidenceToggle: (isOpen: boolean) => void;
	} = $props();

	function badge(): string {
		if (item.severity === 'critical') return 'border-error/30 bg-error/10 text-error';
		if (item.severity === 'warning') return 'border-tertiary/30 bg-tertiary/10 text-tertiary';
		return 'border-primary/25 bg-primary/10 text-primary';
	}

	function accent(): string {
		if (item.severity === 'critical') return 'border-t-error';
		if (item.severity === 'warning') return 'border-t-tertiary';
		return 'border-t-primary';
	}

	function categoryIcon(): string {
		if (item.category === 'index') return 'data_object';
		if (item.category === 'maintenance') return 'cleaning_services';
		if (item.category === 'capacity') return 'monitoring';
		return 'tips_and_updates';
	}

	function destination(): { href: string; label: string } | null {
		if (item.category === 'index') {
			return { href: `/analytics/${databaseId}/index`, label: 'Open index analytics' };
		}
		if (item.category === 'maintenance') {
			return { href: `/schema/${databaseId}`, label: 'Open schema' };
		}
		if (item.category === 'capacity') {
			return { href: `/analytics/${databaseId}/deep`, label: 'Open time travel' };
		}
		return null;
	}

	function formatValue(key: string, value: unknown): string {
		if (value === null || value === undefined) return '--';
		if (key.includes('size_bytes')) return formatBytes(Number(value));
		if (typeof value === 'number') return value.toLocaleString();
		if (Array.isArray(value)) return value.join(', ');
		if (typeof value === 'object') return JSON.stringify(value);
		return String(value);
	}

	function updatedAt(): string {
		return new Intl.DateTimeFormat(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		}).format(new Date(item.last_seen_at));
	}

	function toggleEvidence(event: Event): void {
		onEvidenceToggle((event.currentTarget as HTMLDetailsElement).open);
	}

	const link = $derived(destination());
</script>

<article
	class="flex min-w-0 flex-col overflow-hidden rounded-xl border border-t-4 border-outline-variant bg-surface-container shadow-sm transition hover:-translate-y-0.5 hover:bg-surface-container-high hover:shadow-md {accent()}"
>
	<div class="flex flex-1 flex-col p-4 sm:p-5">
		<div class="flex min-w-0 items-start gap-3">
			<div
				class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-container-highest text-primary"
			>
				<span class="material-symbols-outlined text-[20px]">{categoryIcon()}</span>
			</div>
			<div class="min-w-0 flex-1">
				<div class="mb-2 flex flex-wrap items-center gap-1.5">
					<span class="rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase {badge()}">
						{item.severity}
					</span>
					<span class="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
						{item.category}
					</span>
					<span class="text-[10px] text-on-surface-variant">
						{Math.round(item.confidence * 100)}% confidence
					</span>
				</div>
				<h2 class="m-0 text-base font-bold leading-snug text-on-surface sm:text-lg">
					{item.title}
				</h2>
			</div>
		</div>

		<p class="mt-3 text-sm leading-6 text-on-surface-variant">{item.summary}</p>

		{#if item.recommendation}
			<div class="mt-4 flex-1 rounded-lg border border-primary/15 bg-primary/5 p-3">
				<div
					class="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-primary"
				>
					<span class="material-symbols-outlined text-[16px]">arrow_forward</span>
					Suggested action
				</div>
				<p class="m-0 text-sm leading-5 text-on-surface">{item.recommendation}</p>
			</div>
		{/if}

		{#if Object.keys(item.evidence).length > 0}
			<details
				open={evidenceOpen}
				ontoggle={toggleEvidence}
				class="mt-3 rounded-lg border border-outline-variant/60 bg-surface-container-low"
			>
				<summary class="cursor-pointer px-3 py-2.5 text-xs font-bold text-on-surface-variant">
					Supporting evidence · {Object.keys(item.evidence).length}
				</summary>
				<div class="grid gap-x-4 px-3 pb-3 sm:grid-cols-2 lg:grid-cols-1 2xl:grid-cols-2">
					{#each Object.entries(item.evidence) as [key, value]}
						<div class="min-w-0 border-t border-outline-variant/40 py-2">
							<div class="mb-0.5 text-[10px] capitalize text-on-surface-variant">
								{key.replaceAll('_', ' ')}
							</div>
							<div class="break-words font-code-sm text-xs text-on-surface">
								{formatValue(key, value)}
							</div>
						</div>
					{/each}
				</div>
			</details>
		{/if}

		<div
			class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-outline-variant/50 pt-3"
		>
			<div class="flex min-w-0 items-center gap-2 text-[11px] text-on-surface-variant">
				<span class="material-symbols-outlined text-[15px]">schedule</span>
				<span>Updated {updatedAt()}</span>
				{#if link}
					<span aria-hidden="true">·</span>
					<a
						href={link.href}
						class="inline-flex items-center gap-1 font-bold text-primary hover:underline"
					>
						{link.label}
						<span class="material-symbols-outlined text-[14px]">arrow_outward</span>
					</a>
				{/if}
			</div>
			<div class="ml-auto flex gap-2">
				{#if item.status === 'open'}
					<button
						onclick={() => onUpdate('dismissed')}
						disabled={busy}
						class="rounded-lg px-2.5 py-1.5 text-xs font-bold text-on-surface-variant hover:bg-surface-container-highest disabled:opacity-50"
					>
						Dismiss
					</button>
					<button
						onclick={() => onUpdate('resolved')}
						disabled={busy}
						class="rounded-lg bg-primary px-2.5 py-1.5 text-xs font-bold text-on-primary disabled:opacity-50"
					>
						Resolve
					</button>
				{:else}
					<button
						onclick={() => onUpdate('open')}
						disabled={busy}
						class="rounded-lg border border-primary/30 px-2.5 py-1.5 text-xs font-bold text-primary disabled:opacity-50"
					>
						Reopen
					</button>
				{/if}
			</div>
		</div>
	</div>
</article>
