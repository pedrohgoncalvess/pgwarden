<script lang="ts">
	import { formatBytes, type RetentionPolicy, type RetentionPreview } from '$lib/retention-api';
	let {
		policies,
		selected,
		preview,
		disabled,
		onselect
	}: {
		policies: RetentionPolicy[];
		selected: string;
		preview?: RetentionPreview | null;
		disabled: boolean;
		onselect: (name: string) => void;
	} = $props();
	const date = (value: string | null) => (value ? new Date(value).toLocaleString() : '—');
	const signed = (value: number | null) =>
		value === null ? 'Unavailable' : `${value > 0 ? '+' : ''}${formatBytes(value)}`;
</script>

<section class="settings-card min-w-0 overflow-hidden" aria-labelledby="retention-policies-title">
	<div
		class="flex flex-wrap items-center justify-between gap-2 border-b border-outline-variant px-5 py-4"
	>
		<div>
			<h2 id="retention-policies-title" class="text-sm font-bold">
				{preview?.tables ? 'Impact by table' : 'Current policies'}
			</h2>
			<p class="mt-1 text-xs text-on-surface-variant">
				{preview?.tables
					? 'Review the proposed duration across every affected table.'
					: 'Retention and background job status for all metric tables.'}
			</p>
		</div>
		<span
			class="rounded border border-outline-variant px-2 py-1 font-mono text-[11px] text-on-surface-variant"
			>{policies.length} tables</span
		>
	</div>
	<div class="overflow-x-auto">
		<table class="w-full whitespace-nowrap text-left text-sm">
			<thead
				class="bg-surface-container-low text-[10px] uppercase tracking-wider text-on-surface-variant"
				><tr
					><th scope="col" class="px-5 py-3 font-bold">Metric table</th><th
						scope="col"
						class="px-5 py-3 font-bold">Current retention</th
					><th scope="col" class="px-5 py-3 font-bold">Job status</th>{#if preview?.tables}<th
							scope="col"
							class="px-5 py-3 text-right font-bold">Projected storage</th
						><th scope="col" class="px-5 py-3 text-right font-bold">Policy change</th><th
							scope="col"
							class="px-5 py-3 text-right font-bold">Eligible for removal</th
						>{:else}<th scope="col" class="px-5 py-3 font-bold">Next run</th>{/if}<th
						scope="col"
						class="px-5 py-3 text-right font-bold"><span class="sr-only">Actions</span></th
					></tr
				></thead
			>
			<tbody
				>{#each policies as policy (policy.name)}
					{@const estimate = preview?.tables?.find((item) => item.name === policy.name)}
					<tr
						class="border-t border-outline-variant {selected === policy.name ? 'bg-primary/5' : ''}"
					>
						<th scope="row" class="px-5 py-4 font-mono text-xs font-medium text-on-surface"
							>metric.{policy.name}</th
						>
						<td class="px-5 py-4 font-mono text-xs">{policy.retention_interval ?? 'No policy'}</td>
						<td class="px-5 py-4"
							><span class="inline-flex items-center gap-1.5 text-xs text-on-surface-variant"
								><span class="material-symbols-outlined text-[14px]" aria-hidden="true"
									>{policy.job_id === null
										? 'remove_circle_outline'
										: policy.scheduled
											? 'schedule'
											: 'pause_circle'}</span
								>{policy.job_id === null
									? 'Not configured'
									: policy.scheduled
										? 'Scheduled'
										: 'Paused'}</span
							></td
						>
						{#if preview?.tables}<td class="px-5 py-4 text-right font-mono text-xs tabular-nums"
								>{formatBytes(estimate?.projected_bytes ?? null)}</td
							><td class="px-5 py-4 text-right font-mono text-xs tabular-nums"
								>{signed(estimate?.policy_delta_bytes ?? null)}</td
							><td class="px-5 py-4 text-right font-mono text-xs tabular-nums"
								>{formatBytes(estimate?.reclaimable_bytes ?? null)}</td
							>{:else}<td class="px-5 py-4 text-xs text-on-surface-variant"
								>{date(policy.next_start)}</td
							>{/if}
						<td class="px-5 py-4 text-right"
							><button
								type="button"
								class="rounded px-2 py-1 text-xs font-bold text-primary hover:bg-primary/10 disabled:opacity-40"
								aria-label={`Edit retention for metric.${policy.name}`}
								onclick={() => onselect(policy.name)}
								{disabled}>Edit</button
							></td
						>
					</tr>
				{/each}</tbody
			>
		</table>
	</div>
</section>
