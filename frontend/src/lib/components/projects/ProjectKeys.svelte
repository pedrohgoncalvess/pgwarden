<script lang="ts">
	import { keyStatus, type ProjectKey } from '$lib/projects-api';
	let {
		keys,
		busy,
		onrotate,
		onrevoke
	}: {
		keys: ProjectKey[];
		busy: boolean;
		onrotate: (hours: number) => Promise<void>;
		onrevoke: (id: string) => Promise<void>;
	} = $props();
	let overlap = $state(0);
	const date = (value: string | null) => (value ? new Date(value).toLocaleString() : '—');
</script>

<section class="space-y-4">
	<div class="flex flex-wrap items-end justify-between gap-3">
		<div>
			<h2 class="text-lg font-bold">Ingestion keys</h2>
			<p class="text-xs text-on-surface-variant">
				Full keys are shown once. Revoke a compromised key immediately.
			</p>
		</div>
		<form
			class="flex items-end gap-2"
			onsubmit={(event) => {
				event.preventDefault();
				void onrotate(overlap);
			}}
		>
			<label class="text-xs"
				>Manual overlap (hours)<input
					aria-label="Manual rotation overlap in hours"
					class="mt-1 block w-24 rounded border border-outline-variant bg-surface-container p-2"
					type="number"
					min="0"
					max="168"
					step="1"
					required
					bind:value={overlap}
					disabled={busy}
				/></label
			>
			<button
				class="rounded-lg border border-primary px-3 py-2 text-sm text-primary disabled:opacity-50"
				disabled={busy}>Rotate key</button
			>
		</form>
	</div>
	<p class="text-xs text-on-surface-variant">
		Zero overlap invalidates every previous key immediately. Automatic rotation uses the overlap in
		project settings.
	</p>
	<div class="overflow-x-auto">
		<table class="w-full text-left text-xs">
			<thead class="text-on-surface-variant"
				><tr
					><th class="p-2">Key</th><th class="p-2">Status</th><th class="p-2">Expires / retires</th
					><th class="p-2">Last used</th><th class="p-2">Action</th></tr
				></thead
			>
			<tbody
				>{#each keys as key (key.id)}
					<tr class="border-t border-outline-variant"
						><td class="p-2 font-mono">{key.prefix}…</td><td class="p-2">{keyStatus(key)}</td><td
							class="p-2"
							>{key.expires_at ? date(key.expires_at) : 'No expiration'}<br />{key.retire_at
								? `Retires ${date(key.retire_at)}`
								: ''}</td
						><td class="p-2">{date(key.last_used_at)}</td><td class="p-2"
							><button
								class="text-error disabled:opacity-40"
								disabled={busy || ['Revoked', 'Expired', 'Retired'].includes(keyStatus(key))}
								onclick={() => {
									if (confirm('Revoke this key immediately?')) void onrevoke(key.id);
								}}>Revoke</button
							></td
						></tr
					>
				{/each}</tbody
			>
		</table>
	</div>
</section>
