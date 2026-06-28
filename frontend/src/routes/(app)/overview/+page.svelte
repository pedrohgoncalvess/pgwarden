<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { listDatabases } from '$lib/api';

  let error = $state('');

  onMount(async () => {
    try {
      const databases = await listDatabases();
      if (databases.length > 0) {
        await goto(`/overview/${databases[0].id}`, { replaceState: true });
      } else {
        await goto('/servers', { replaceState: true });
      }
    } catch (err: any) {
      if (err.message?.includes('401')) {
        localStorage.removeItem('token');
        window.location.href = '/login';
        return;
      }
      error = err.message || 'Failed to load databases.';
    }
  });
</script>

{#if error}
  <div class="p-4">
    <div class="rounded-lg border border-error/30 bg-error-container/10 p-4 text-sm text-error">
      {error}
    </div>
  </div>
{/if}
