<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';

	onMount(() => {
		const queryString = $page.url.search;
		goto(`/search${queryString}`, { replaceState: true });
	});
</script>

<div class="pt-24 px-container-padding pb-12">
	<div class="rounded-lg border border-outline-variant bg-surface-container px-6 py-16 text-center">
		<span class="material-symbols-outlined mb-3 text-[40px] text-on-surface-variant">search</span>
		<p class="mb-1 font-bold text-on-surface">Opening search...</p>
	</div>
</div>
