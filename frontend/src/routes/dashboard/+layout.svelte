<script lang="ts">
  import { page } from '$app/stores';

  let { children } = $props();

  const navItems = [
    { name: 'Overview', href: '/dashboard', icon: 'dashboard' },
    { name: 'Schema view', href: '/dashboard/schemas', icon: 'account_tree' },
    { name: 'Servers', href: '/dashboard/servers', icon: 'dns' },
    { name: 'Databases', href: '/dashboard/databases', icon: 'database' },
    { name: 'Sessions', href: '/dashboard/sessions', icon: 'group' },
    { name: 'Processes', href: '/dashboard/processes', icon: 'precision_manufacturing' },
  ];

  const metadataItems = [
    { name: 'Tags', href: '/dashboard/tags', icon: 'label' },
    { name: 'Documentações', href: '/dashboard/docs', icon: 'description' }
  ];

  const configItems = [
    { name: 'Settings', href: '/dashboard/settings', icon: 'settings' }
  ];

  let expandedMetadata = $state($page.url.pathname.startsWith('/dashboard/tags') || $page.url.pathname.startsWith('/dashboard/docs'));

  function isActive(href: string, currentPath: string) {
    if (href === '/dashboard') {
      return currentPath === href;
    }
    return currentPath.startsWith(href);
  }
</script>

<!-- Body classes applied in the global wrapping level -->
<div class="bg-background text-on-background selection:bg-primary-container selection:text-on-primary-container min-h-screen">
  
  <!-- Sidebar / NavigationDrawer -->
  <aside class="h-screen w-64 fixed left-0 top-0 bg-surface-container-low border-r border-outline-variant flex flex-col py-4 gap-stack-sm z-50">
    <div class="px-6 mb-6 flex items-center gap-3">
      <div class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary font-bold">W</div>
      <span class="font-headline-md text-headline-md font-bold text-primary">pgwarden</span>
    </div>

    <div class="flex-1 overflow-y-auto px-3 space-y-6 custom-scrollbar">
      
      <!-- Main Nav -->
      <nav class="space-y-1">
        <h2 class="px-3 text-[10px] font-label-caps text-on-surface-variant uppercase tracking-widest mb-2">Menu</h2>
        {#each navItems as item}
          {@const active = isActive(item.href, $page.url.pathname)}
          <a
            href={item.href}
            class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group {active ? 'bg-secondary-container text-on-secondary-container font-bold rounded-lg' : 'text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg'}"
          >
            <span class="material-symbols-outlined mr-3" style="{active ? 'font-variation-settings: \'FILL\' 1;' : ''}">{item.icon}</span>
            <span class="font-body-md text-body-md">{item.name}</span>
          </a>
        {/each}
      </nav>

      <!-- Metadata Nav -->
      <nav class="space-y-1">
        <h2 class="px-3 text-[10px] font-label-caps text-on-surface-variant uppercase tracking-widest mb-2">Metadata</h2>
        <button
          onclick={() => expandedMetadata = !expandedMetadata}
          class="w-full flex items-center justify-between px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
        >
          <div class="flex items-center">
            <span class="material-symbols-outlined mr-3" style="font-variation-settings: 'FILL' 0;">folder_managed</span>
            <span class="font-body-md text-body-md">Metadata</span>
          </div>
          <span class="material-symbols-outlined text-[18px] transition-transform duration-200" style="transform: rotate({expandedMetadata ? 180 : 0}deg)">expand_more</span>
        </button>
        {#if expandedMetadata}
          <div class="ml-4 pl-4 border-l border-outline-variant/50 space-y-1">
            {#each metadataItems as item}
              {@const active = isActive(item.href, $page.url.pathname)}
              <a
                href={item.href}
                class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group {active ? 'bg-secondary-container text-on-secondary-container font-bold rounded-lg' : 'text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg'}"
              >
                <span class="material-symbols-outlined mr-3" style="{active ? 'font-variation-settings: \'FILL\' 1;' : ''}">{item.icon}</span>
                <span class="font-body-md text-body-md">{item.name}</span>
              </a>
            {/each}
          </div>
        {/if}
      </nav>

      <!-- System Nav -->
      <nav class="space-y-1">
        <h2 class="px-3 text-[10px] font-label-caps text-on-surface-variant uppercase tracking-widest mb-2">System</h2>
        {#each configItems as item}
          {@const active = isActive(item.href, $page.url.pathname)}
          <a
            href={item.href}
            class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group {active ? 'bg-secondary-container text-on-secondary-container font-bold rounded-lg' : 'text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg'}"
          >
            <span class="material-symbols-outlined mr-3" style="{active ? 'font-variation-settings: \'FILL\' 1;' : ''}">{item.icon}</span>
            <span class="font-body-md text-body-md">{item.name}</span>
          </a>
        {/each}
      </nav>

    </div>

    <!-- User Profile & Logout -->
    <div class="px-6 py-4 mt-auto border-t border-outline-variant flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-xs">DBA</div>
        <div class="overflow-hidden">
          <p class="font-body-sm text-body-sm font-bold truncate text-on-surface">admin</p>
          <p class="text-[10px] text-on-surface-variant truncate">Session Active</p>
        </div>
      </div>
      <button 
        onclick={() => {
          localStorage.removeItem('token');
          window.location.href = '/login';
        }}
        class="text-on-surface-variant hover:text-error transition-colors"
        title="Logout"
      >
        <span class="material-symbols-outlined text-[20px]">logout</span>
      </button>
    </div>
  </aside>

  <!-- Main Content Area -->
  <main class="ml-64 min-h-screen">
    {@render children()}
  </main>
</div>
