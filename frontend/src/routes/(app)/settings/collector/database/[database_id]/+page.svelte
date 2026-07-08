<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	onMount(() => {
		goto(`/runs/${$page.params.database_id}/settings/database`, { replaceState: true });
	});
</script>

<div class="px-container-padding pb-12 pt-24">
	<div class="settings-card px-6 py-16 flex flex-col items-center text-center">
		<span class="material-symbols-outlined text-[48px] text-on-surface-variant mb-4">database</span>
		<p class="font-bold text-on-surface text-lg mb-2">Opening database collector settings...</p>
	</div>
</div>

<style>
	.settings-card {
		background: rgba(26, 33, 31, 0.95);
		border: 1px solid rgba(133, 148, 144, 0.15);
		border-radius: 14px;
	}
</style>
