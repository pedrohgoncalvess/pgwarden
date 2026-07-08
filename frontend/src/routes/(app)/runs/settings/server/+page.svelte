<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { listServers } from '$lib/api';

	let loading = $state(true);
	let error = $state('');

	onMount(async () => {
		try {
			const servers = await listServers();
			if (servers[0]) {
				await goto(`/runs/${servers[0].id}/settings/server`, { replaceState: true });
			} else {
				loading = false;
			}
		} catch (err: any) {
			if (err.message?.includes('401')) {
				localStorage.removeItem('token');
				window.location.href = '/login';
				return;
			}
			error = err.message || 'Failed to load servers.';
			loading = false;
		}
	});
</script>

<div class="pt-24 px-container-padding pb-12">
	<div class="settings-card px-6 py-16 flex flex-col items-center text-center">
		<span class="material-symbols-outlined text-[48px] text-on-surface-variant mb-4">dns</span>
		<p class="font-bold text-on-surface text-lg mb-2">Server-level collector settings</p>
		<p class="text-sm text-on-surface-variant max-w-xs">
			{#if loading}
				Opening server collector settings...
			{:else if error}
				{error}
			{:else}
				No servers registered.
			{/if}
		</p>
	</div>
</div>

<style>
	.settings-card {
		background: rgba(26, 33, 31, 0.95);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 14px;
	}
</style>
