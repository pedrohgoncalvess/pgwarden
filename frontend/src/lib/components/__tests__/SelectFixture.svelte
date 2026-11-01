<script lang="ts">
	import Select from '../Select.svelte';
	import type { SelectOption } from '$lib/selectNavigation';
	let { options, onchange }: { options: SelectOption[]; onchange: (value: string) => void } =
		$props();
	let value = $state('main');
</script>

<Select
	{options}
	bind:value
	name="database"
	aria-label="Database"
	onchange={() => onchange(value)}
/>
<output>{value}</output>
