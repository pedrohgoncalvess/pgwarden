<script lang="ts">
	import Spinner from '$lib/components/Spinner.svelte';
	import { formatBytes, type RetentionPreview } from '$lib/retention-api';
	let {
		preview,
		fresh,
		busy,
		saving,
		global,
		count,
		onsave
	}: {
		preview: RetentionPreview | null;
		fresh: boolean;
		busy: boolean;
		saving: boolean;
		global: boolean;
		count: number;
		onsave: () => void;
	} = $props();
	const signed = (value: number | null) =>
		value === null ? 'Unavailable' : `${value > 0 ? '+' : ''}${formatBytes(value)}`;
	const date = (value: string | null) => (value ? new Date(value).toLocaleString() : '—');
</script>

<section
	class="settings-card flex min-w-0 flex-col overflow-hidden"
	aria-labelledby="retention-impact-title"
	aria-busy={busy}
>
	<div class="flex items-center justify-between gap-3 border-b border-outline-variant px-5 py-4">
		<div class="flex items-center gap-2">
			<span class="material-symbols-outlined text-[18px] text-on-surface-variant" aria-hidden="true"
				>query_stats</span
			>
			<h2 id="retention-impact-title" class="text-sm font-bold">Storage impact</h2>
		</div>
		{#if preview && fresh}<span
				class="rounded border border-primary/25 bg-primary/10 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-primary"
				>Estimate ready</span
			>{/if}
	</div>
	<div class="flex flex-1 flex-col p-5" aria-live="polite">
		{#if busy && !saving}
			<div class="flex min-h-64 flex-1 flex-col items-center justify-center gap-3 text-center">
				<Spinner class="text-2xl text-primary" />
				<p class="text-sm font-bold">Estimating storage impact</p>
				<p class="max-w-xs text-xs leading-relaxed text-on-surface-variant">
					Reading chunk sizes and collection history for {global
						? 'all metric tables'
						: 'the selected table'}.
				</p>
			</div>
		{:else if preview && fresh}
			{#if preview.logical}<p class="mb-3 text-xs text-on-surface-variant">
					Logical row volume for servers inheriting this default. Project and server overrides are
					preserved. These values do not represent immediate disk savings.
				</p>{/if}
			<p class="mb-5 text-xs text-on-surface-variant">
				Keep {preview.window.value}
				{preview.window.unit} · {global ? `${count} metric tables` : `metric.${preview.name}`}
			</p>
			<div class="grid grid-cols-1 gap-5 sm:grid-cols-3">
				{#each [['Current storage', formatBytes(preview.current_bytes)], ['Projected storage', formatBytes(preview.projected_bytes)], ['Change vs. current policy', signed(preview.policy_delta_bytes)]] as [label, value]}
					<div class="min-w-0">
						<p class="text-xs leading-relaxed text-on-surface-variant">{label}</p>
						<p class="mt-2 break-words font-mono text-xl font-medium tabular-nums text-on-surface">
							{value}
						</p>
					</div>
				{/each}
			</div>
			<div
				class="mt-6 flex gap-3 rounded-lg border border-outline-variant bg-surface-container-low p-4"
			>
				<span
					class="material-symbols-outlined shrink-0 text-[18px] {preview.reclaimable_bytes > 0
						? 'text-status-warning'
						: 'text-on-surface-variant'}"
					aria-hidden="true">{preview.reclaimable_bytes > 0 ? 'delete_sweep' : 'info'}</span
				>
				<div class="space-y-1">
					<p class="text-sm font-bold">
						{formatBytes(preview.reclaimable_bytes)} eligible for removal
					</p>
					<p class="text-xs leading-relaxed text-on-surface-variant">
						{#if preview.logical}{preview.expired_rows} rows can expire under this default. Cleanup runs
							in batches every minute; removed history cannot be restored.{:else}{preview.eligible_chunks}
							complete chunks can expire under this policy. Cleanup runs on the existing schedule; removed
							history cannot be restored.{/if}
					</p>
				</div>
			</div>
			{#if preview.confidence === 'insufficient_data'}<p
					class="mt-4 flex gap-2 text-xs leading-relaxed text-status-warning"
				>
					<span class="material-symbols-outlined shrink-0 text-[16px]" aria-hidden="true">info</span
					>Some tables have insufficient history to project growth. Existing storage and removal
					eligibility are still available.
				</p>{/if}
			<details class="mt-5 border-t border-outline-variant pt-4">
				<summary class="cursor-pointer text-xs font-medium text-on-surface-variant"
					>How this estimate is calculated</summary
				>
				<dl class="mt-4 grid grid-cols-1 gap-3 text-xs sm:grid-cols-2">
					{#each [['Observed average / day', formatBytes(preview.bytes_per_day)], ['Current policy projection', formatBytes(preview.baseline_projected_bytes)], ['Change vs. occupied storage', signed(preview.footprint_delta_bytes)], ['Chunks / compressed', `${preview.total_chunks} / ${preview.compressed_chunks}`]] as [label, value]}<div
						>
							<dt class="text-on-surface-variant">{label}</dt>
							<dd class="mt-1 font-mono">{value}</dd>
						</div>{/each}
				</dl>
				{#if preview.logical}<p class="mt-4 text-xs leading-relaxed text-on-surface-variant">
						Estimated logical row sizes exclude indexes, compression and free pages. Deletion makes
						storage reusable and does not guarantee filesystem shrinkage. The projection assumes the
						observed collection rate continues.
					</p>{:else}<p class="mt-4 text-xs leading-relaxed text-on-surface-variant">
						Physical chunk bytes, including indexes, TOAST and compression, are averaged from the
						first sample to now. Projections assume the same collection volume and compression mix.
						They describe an approximate steady-state footprint, not an immediate disk change.
					</p>
					<p class="mt-3 text-xs leading-relaxed text-on-surface-variant">
						TimescaleDB expires complete chunks. Short retention windows may keep more data until a
						chunk fully expires. Increasing retention collects future history and does not restore
						previously removed data.
					</p>{/if}
				{#if global}<p class="mt-3 text-xs leading-relaxed text-on-surface-variant">
						Consolidated projections require enough history for every table. Comparing policies also
						requires an existing retention limit on every table. Individual estimates remain
						available below.
					</p>{/if}
				<p class="mt-3 text-xs text-on-surface-variant">
					Observed {date(preview.first_sample)} – {date(preview.last_sample)}. Measured {date(
						preview.measured_at
					)}.
				</p>
			</details>
		{:else}
			<div class="flex min-h-64 flex-1 flex-col items-center justify-center text-center">
				<div
					class="mb-4 flex h-11 w-11 items-center justify-center rounded-lg border border-outline-variant bg-surface-container-high"
				>
					<span
						class="material-symbols-outlined text-[22px] text-on-surface-variant"
						aria-hidden="true">{preview ? 'update' : 'data_usage'}</span
					>
				</div>
				<p class="text-sm font-bold">
					{preview ? 'Estimate needs updating' : 'Review before applying'}
				</p>
				<p class="mt-2 max-w-xs text-xs leading-relaxed text-on-surface-variant">
					{preview
						? 'The duration changed. Estimate again to refresh the preview before saving.'
						: 'Choose a retention period and estimate its impact to compare storage and see what can be removed.'}
				</p>
			</div>
		{/if}
	</div>
	<div
		class="flex flex-wrap items-center justify-between gap-4 border-t border-outline-variant bg-surface-container-low px-5 py-4"
	>
		<p class="max-w-xs text-xs leading-relaxed text-on-surface-variant">
			{global
				? `Applies to all ${count} current metric tables.`
				: 'Applies to the selected metric table.'}
		</p>
		<button
			type="button"
			class="btn-primary flex items-center justify-center gap-2 px-4 py-2 text-sm font-bold disabled:cursor-not-allowed disabled:opacity-40"
			onclick={onsave}
			disabled={busy || !fresh}
			>{#if saving}<Spinner class="text-base" />{:else}<span
					class="material-symbols-outlined text-[16px]"
					aria-hidden="true">check</span
				>{/if}{saving
				? 'Saving…'
				: global
					? 'Save retention for all tables'
					: 'Save retention'}</button
		>
	</div>
</section>
