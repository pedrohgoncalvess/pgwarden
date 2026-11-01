<script lang="ts">
	let { class: className = '' }: { class?: string } = $props();
</script>

<svg
	class="loading-spinner animate-spin {className}"
	viewBox="0 0 24 24"
	fill="none"
	role="status"
	aria-label="Loading"
>
	<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2.5" opacity="0.2" />
	<path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" />
</svg>

<style>
	.loading-spinner {
		display: inline-block;
		width: 1em;
		height: 1em;
		flex-shrink: 0;
		vertical-align: middle;
		transform-origin: center;
	}
</style>
