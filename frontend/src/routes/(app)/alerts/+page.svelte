<script lang="ts">
	const title = 'Alerts';
	const icon = 'notifications';
</script>


<header
	class="fixed top-0 right-0 w-[calc(100%-16rem)] z-40 bg-surface-dim border-b border-outline-variant flex items-center px-container-padding h-16 gap-3"
>
	<span class="material-symbols-outlined text-on-surface-variant">{icon}</span>
	<h1 class="font-headline-md text-headline-md text-on-background m-0">{title}</h1>
</header>


<div class="pt-24 px-container-padding pb-12">
	<div class="settings-card px-6 py-16 flex flex-col items-center text-center">
		<span class="material-symbols-outlined text-[48px] text-on-surface-variant mb-4">{icon}</span>
		<p class="font-bold text-on-surface text-lg mb-2">{title}</p>
		<p class="text-sm text-on-surface-variant max-w-xs">
			This section is coming soon. Check back in a future release.
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
