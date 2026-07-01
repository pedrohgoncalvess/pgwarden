<script lang="ts">
	import { page } from '$app/stores';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';

	let { children } = $props();

	const navItems = [
		{ name: 'Overview', href: '/overview', icon: 'dashboard', needsDb: true },
		{ name: 'Schema', href: '/schema', icon: 'account_tree', needsDb: true },
		{ name: 'Servers', href: '/servers', icon: 'dns', needsDb: false }
	];

	const analyticsItems = [
		{ name: 'Data', href: '/analytics/data', icon: 'bar_chart', needsDb: true },
		{ name: 'Query', href: '/analytics/query', icon: 'search', needsDb: true },
		{ name: 'Index', href: '/analytics/index', icon: 'speed', needsDb: true }
	];

	const runItems = [
		{ name: 'Live', href: '/runs/live', icon: 'bolt', needsDb: true },
		{ name: 'History', href: '/runs/history', icon: 'history', needsDb: true }
	];

	const metadataItems = [
		{ name: 'Tags', href: '/metadata/tags', icon: 'label', needsDb: false },
		{ name: 'Documentation', href: '/metadata/documentation', icon: 'description', needsDb: false }
	];

	const settingsItems = [
		{ name: 'Connections', href: '/settings/connections', icon: 'lan', needsDb: false },
		{ name: 'Alerts', href: '/settings/alerts', icon: 'notifications', needsDb: false },
		{ name: 'Account', href: '/settings/account', icon: 'manage_accounts', needsDb: false }
	];

	const collectorItems = [
		{ name: 'Server', href: '/settings/collector/server', icon: 'dns', needsDb: false },
		{ name: 'Database', href: '/settings/collector/database', icon: 'database', needsDb: false }
	];

	let expandedAnalytics = $state($page.url.pathname.startsWith('/analytics'));
	let expandedRuns = $state($page.url.pathname.startsWith('/runs'));
	let expandedMetadata = $state($page.url.pathname.startsWith('/metadata'));
	let expandedSettings = $state($page.url.pathname.startsWith('/settings'));
	let expandedSettingsCollector = $state($page.url.pathname.startsWith('/settings/collector'));

	function resolveHref(href: string, needsDb: boolean, dbId: string | null): string {
		if (!needsDb) return href;
		const activeDb = dbId ?? $selectedDatabaseId;
		if (!activeDb) {
			if (href.startsWith('/runs/')) return '/runs';
			if (href.startsWith('/analytics/')) return '/analytics';
			return href;
		}
		if (href.startsWith('/runs/')) {
			return `/runs/${activeDb}${href.slice('/runs'.length)}`;
		}
		if (href.startsWith('/analytics/')) {
			return `/analytics/${activeDb}${href.slice('/analytics'.length)}`;
		}
		return `${href}/${activeDb}`;
	}

	$effect(() => {
		const routeDbId = $page.params.database_id;
		const currentPath = $page.url.pathname;

		if (routeDbId) {
			selectedDatabaseId.set(routeDbId);
		}

		if (isActive('/analytics', currentPath)) expandedAnalytics = true;
		if (isActive('/runs', currentPath)) expandedRuns = true;
		if (isActive('/metadata', currentPath)) expandedMetadata = true;
		if (isActive('/settings', currentPath)) expandedSettings = true;
		if (isActive('/settings/collector', currentPath)) expandedSettingsCollector = true;
	});

	function isActive(href: string, currentPath: string) {
		return currentPath === href || currentPath.startsWith(`${href}/`);
	}

	function normalizeSubmenuPath(path: string) {
		const segments = path.split('/').filter(Boolean);
		const section = segments[0];

		if ((section === 'analytics' || section === 'runs') && segments.length >= 3) {
			return `/${section}/${segments.slice(2).join('/')}`;
		}

		return path;
	}

	function isSubmenuActive(href: string, currentPath: string) {
		return isActive(href, normalizeSubmenuPath(currentPath));
	}
</script>

<!-- Body classes applied in the global wrapping level -->
<div
	class="bg-background text-on-background selection:bg-primary-container selection:text-on-primary-container min-h-screen"
>
	<!-- Sidebar / NavigationDrawer -->
	<aside
		class="h-screen w-64 fixed left-0 top-0 bg-surface-container-low border-r border-outline-variant flex flex-col py-4 gap-stack-sm z-50"
	>
		<div class="px-6 mb-6 flex items-center gap-3">
			<div
				class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary font-bold"
			>
				W
			</div>
			<span class="font-headline-md text-headline-md font-bold text-primary">pgwarden</span>
		</div>

		<div class="flex-1 overflow-y-auto px-3 space-y-2 custom-scrollbar">
			<!-- Main Nav -->
			<nav class="space-y-1">
				<h2
					class="px-3 text-[10px] font-label-caps text-on-surface-variant uppercase tracking-widest mb-2"
				>
					Menu
				</h2>
				{#each navItems as item}
					{@const href = resolveHref(item.href, item.needsDb, $page.params.database_id ?? null)}
					{@const active = isActive(item.href, $page.url.pathname)}
					<a
						{href}
						class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group {active
							? 'bg-secondary-container text-on-secondary-container font-bold rounded-lg'
							: 'text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg'}"
					>
						<span
							class="material-symbols-outlined mr-3"
							style={active ? "font-variation-settings: 'FILL' 1;" : ''}>{item.icon}</span
						>
						<span class="font-body-md text-body-md">{item.name}</span>
					</a>
				{/each}
			</nav>

			<!-- Analytics Nav -->
			<nav class="space-y-1">
				<button
					onclick={() => (expandedAnalytics = !expandedAnalytics)}
					class="w-full flex items-center justify-between px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
				>
					<div class="flex items-center">
						<span class="material-symbols-outlined mr-3" style="font-variation-settings: 'FILL' 0;"
							>analytics</span
						>
						<span class="font-body-md text-body-md">Analytics</span>
					</div>
					<span
						class="material-symbols-outlined text-[18px] transition-transform duration-200"
						style="transform: rotate({expandedAnalytics ? 180 : 0}deg)">expand_more</span
					>
				</button>
				{#if expandedAnalytics}
					<div class="ml-4 pl-4 border-l border-outline-variant/50 space-y-1">
						{#each analyticsItems as item}
							{@const href = resolveHref(item.href, item.needsDb, $page.params.database_id ?? null)}
							{@const active = isSubmenuActive(item.href, $page.url.pathname)}
							{#if active}
								<a
									href={$page.url.pathname}
									aria-current="page"
									class="flex items-center px-3 py-2 transition-colors cursor-default pointer-events-none group bg-secondary-container text-on-secondary-container font-bold rounded-lg"
								>
									<span
										class="material-symbols-outlined mr-3"
										style="font-variation-settings: 'FILL' 1;">{item.icon}</span
									>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{:else}
								<a
									{href}
									class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
								>
									<span class="material-symbols-outlined mr-3">{item.icon}</span>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{/if}
						{/each}
					</div>
				{/if}
			</nav>

			<!-- Runs Nav -->
			<nav class="space-y-1">
				<button
					onclick={() => (expandedRuns = !expandedRuns)}
					class="w-full flex items-center justify-between px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
				>
					<div class="flex items-center">
						<span class="material-symbols-outlined mr-3" style="font-variation-settings: 'FILL' 0;"
							>precision_manufacturing</span
						>
						<span class="font-body-md text-body-md">Runs</span>
					</div>
					<span
						class="material-symbols-outlined text-[18px] transition-transform duration-200"
						style="transform: rotate({expandedRuns ? 180 : 0}deg)">expand_more</span
					>
				</button>
				{#if expandedRuns}
					<div class="ml-4 pl-4 border-l border-outline-variant/50 space-y-1">
						{#each runItems as item}
							{@const href = resolveHref(item.href, item.needsDb, $page.params.database_id ?? null)}
							{@const active = isSubmenuActive(item.href, $page.url.pathname)}
							{#if active}
								<a
									href={$page.url.pathname}
									aria-current="page"
									class="flex items-center px-3 py-2 transition-colors cursor-default pointer-events-none group bg-secondary-container text-on-secondary-container font-bold rounded-lg"
								>
									<span
										class="material-symbols-outlined mr-3"
										style="font-variation-settings: 'FILL' 1;">{item.icon}</span
									>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{:else}
								<a
									{href}
									class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
								>
									<span class="material-symbols-outlined mr-3">{item.icon}</span>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{/if}
						{/each}
					</div>
				{/if}
			</nav>

			<!-- Metadata Nav -->
			<nav class="space-y-1">
				<button
					onclick={() => (expandedMetadata = !expandedMetadata)}
					class="w-full flex items-center justify-between px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
				>
					<div class="flex items-center">
						<span class="material-symbols-outlined mr-3" style="font-variation-settings: 'FILL' 0;"
							>folder_managed</span
						>
						<span class="font-body-md text-body-md">Metadata</span>
					</div>
					<span
						class="material-symbols-outlined text-[18px] transition-transform duration-200"
						style="transform: rotate({expandedMetadata ? 180 : 0}deg)">expand_more</span
					>
				</button>
				{#if expandedMetadata}
					<div class="ml-4 pl-4 border-l border-outline-variant/50 space-y-1">
						{#each metadataItems as item}
							{@const active = isSubmenuActive(item.href, $page.url.pathname)}
							{#if active}
								<a
									href={$page.url.pathname}
									aria-current="page"
									class="flex items-center px-3 py-2 transition-colors cursor-default pointer-events-none group bg-secondary-container text-on-secondary-container font-bold rounded-lg"
								>
									<span
										class="material-symbols-outlined mr-3"
										style="font-variation-settings: 'FILL' 1;">{item.icon}</span
									>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{:else}
								<a
									href={item.href}
									class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
								>
									<span class="material-symbols-outlined mr-3">{item.icon}</span>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{/if}
						{/each}
					</div>
				{/if}
			</nav>

			<!-- Settings Nav -->
			<nav class="space-y-1">
				<button
					onclick={() => (expandedSettings = !expandedSettings)}
					class="w-full flex items-center justify-between px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
				>
					<div class="flex items-center">
						<span class="material-symbols-outlined mr-3" style="font-variation-settings: 'FILL' 0;"
							>settings</span
						>
						<span class="font-body-md text-body-md">Settings</span>
					</div>
					<span
						class="material-symbols-outlined text-[18px] transition-transform duration-200"
						style="transform: rotate({expandedSettings ? 180 : 0}deg)">expand_more</span
					>
				</button>
				{#if expandedSettings}
					<div class="ml-4 pl-4 border-l border-outline-variant/50 space-y-1">
						{#each settingsItems as item}
							{@const href = resolveHref(item.href, item.needsDb, $page.params.database_id ?? null)}
							{@const active = isSubmenuActive(item.href, $page.url.pathname)}
							{#if active}
								<a
									href={$page.url.pathname}
									aria-current="page"
									class="flex items-center px-3 py-2 transition-colors cursor-default pointer-events-none group bg-secondary-container text-on-secondary-container font-bold rounded-lg"
								>
									<span
										class="material-symbols-outlined mr-3"
										style="font-variation-settings: 'FILL' 1;">{item.icon}</span
									>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{:else}
								<a
									{href}
									class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
								>
									<span class="material-symbols-outlined mr-3">{item.icon}</span>
									<span class="font-body-md text-body-md">{item.name}</span>
								</a>
							{/if}
						{/each}

						<!-- Collector nested dropdown -->
						<div class="space-y-1">
							<button
								onclick={() => (expandedSettingsCollector = !expandedSettingsCollector)}
								class="w-full flex items-center justify-between px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
							>
								<div class="flex items-center">
									<span class="material-symbols-outlined mr-3">radar</span>
									<span class="font-body-md text-body-md">Collector</span>
								</div>
								<span
									class="material-symbols-outlined text-[18px] transition-transform duration-200"
									style="transform: rotate({expandedSettingsCollector ? 180 : 0}deg)"
									>expand_more</span
								>
							</button>
							{#if expandedSettingsCollector}
								<div class="ml-4 pl-4 border-l border-outline-variant/50 space-y-1">
									{#each collectorItems as item}
										{@const href = resolveHref(item.href, item.needsDb, $page.params.database_id ?? null)}
										{@const active = isSubmenuActive(item.href, $page.url.pathname)}
										{#if active}
											<a
												href={$page.url.pathname}
												aria-current="page"
												class="flex items-center px-3 py-2 transition-colors cursor-default pointer-events-none group bg-secondary-container text-on-secondary-container font-bold rounded-lg"
											>
												<span
													class="material-symbols-outlined mr-3"
													style="font-variation-settings: 'FILL' 1;"
													>{item.icon}</span
												>
												<span class="font-body-md text-body-md">{item.name}</span>
											</a>
										{:else}
											<a
												{href}
												class="flex items-center px-3 py-2 transition-colors cursor-pointer active:scale-95 group text-on-surface-variant hover:bg-surface-variant hover:text-on-surface rounded-lg"
											>
												<span class="material-symbols-outlined mr-3">{item.icon}</span>
												<span class="font-body-md text-body-md">{item.name}</span>
											</a>
										{/if}
									{/each}
								</div>
							{/if}
						</div>
					</div>
				{/if}
			</nav>
		</div>

		<!-- User Profile & Logout -->
		<div
			class="px-6 py-4 mt-auto border-t border-outline-variant flex items-center justify-between"
		>
			<div class="flex items-center gap-3">
				<div
					class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-xs"
				>
					DBA
				</div>
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
