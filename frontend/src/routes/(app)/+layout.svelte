<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { redirectToLogin, validateSession } from '$lib/auth';
	import NotificationPanel from '$lib/components/NotificationPanel.svelte';
	import { listDatabases, listServers } from '$lib/api';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';

	let { children } = $props();

	const navItems = [
		{ name: 'Search', href: '/search', icon: 'search', needsDb: false },
		{ name: 'Overview', href: '/overview', icon: 'grid_view', needsDb: true },
		{ name: 'Schema', href: '/schema', icon: 'schema', needsDb: true },
		{ name: 'Servers', href: '/servers', icon: 'dns', needsDb: false }
	];

	const analyticsItems = [
		{ name: 'Data', href: '/analytics/data', icon: 'bar_chart', needsDb: true },
		{ name: 'Query', href: '/analytics/query', icon: 'search', needsDb: true },
		{ name: 'Index', href: '/analytics/index', icon: 'data_object', needsDb: true },
		{
			name: 'Recommendations',
			href: '/analytics/recommendations',
			icon: 'tips_and_updates',
			needsDb: true
		},
		{ name: 'Time travel', href: '/analytics/deep', icon: 'history_toggle_off', needsDb: true }
	];

	const runItems = [
		{ name: 'Live', href: '/runs/live', icon: 'bolt', needsDb: true },
		{ name: 'History', href: '/runs/history', icon: 'history', needsDb: true }
	];

	const runSettingsItems = [
		{ name: 'Server', href: '/runs', suffix: '/settings/server', idType: 'server', icon: 'dns' },
		{
			name: 'Database',
			href: '/runs',
			suffix: '/settings/database',
			idType: 'database',
			icon: 'database'
		},
		{ name: 'Services', href: '/runs/settings/services', idType: 'services', icon: 'hub' }
	];

	const metadataItems = [
		{ name: 'Documentation', href: '/metadata/documentation', icon: 'description' },
		{ name: 'Tags', href: '/metadata/tag', icon: 'label' }
	];

	const settingsItems = [
		{ name: 'Connections', href: '/settings/connections', icon: 'lan', needsDb: false },
		{ name: 'Account', href: '/settings/account', icon: 'manage_accounts', needsDb: false }
	];

	const alertsItems = [
		{ name: 'Server', href: '/alerts/server', icon: 'dns' },
		{ name: 'Database', href: '/alerts/database', icon: 'database' },
		{ name: 'Table', href: '/alerts/table', icon: 'table' },
		{ name: 'Index', href: '/alerts/index', icon: 'data_object' },
		{ name: 'Configuration', href: '/alerts/configuration', icon: 'settings' }
	];

	let expandedAnalytics = $state($page.url.pathname.startsWith('/analytics'));
	let expandedAlerts = $state($page.url.pathname.startsWith('/alerts'));
	let expandedRuns = $state($page.url.pathname.startsWith('/runs'));
	let expandedRunsSettings = $state(
		/^\/runs\/[^/]+\/settings\/(server|database)/.test($page.url.pathname)
	);
	let expandedMetadata = $state($page.url.pathname.startsWith('/metadata'));
	let expandedSettings = $state($page.url.pathname.startsWith('/settings'));
	let notificationsOpen = $state(false);
	let notificationCount = $state(0);
	let routeError = $state('');
	let checkedRoute = $state('');
	let routeErrorTimeout: number | null = null;
	let authState = $state<'checking' | 'authenticated' | 'unavailable'>('checking');
	let lastValidatedAt = 0;

	async function checkSession(blockPage = false) {
		if (blockPage) authState = 'checking';
		const result = await validateSession();
		if (result === 'valid') {
			lastValidatedAt = Date.now();
			authState = 'authenticated';
		} else if (result === 'unavailable' && authState !== 'authenticated') {
			authState = 'unavailable';
		}
	}

	onMount(() => {
		void checkSession(true);
		const interval = window.setInterval(() => void checkSession(), 60_000);
		const validateActiveSession = () => {
			if (document.visibilityState === 'visible') void checkSession();
		};
		window.addEventListener('focus', validateActiveSession);
		document.addEventListener('visibilitychange', validateActiveSession);
		return () => {
			window.clearInterval(interval);
			window.removeEventListener('focus', validateActiveSession);
			document.removeEventListener('visibilitychange', validateActiveSession);
		};
	});

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

	function resolveMetadataHref(href: string): string {
		if (href === '/metadata/documentation') {
			const activeDb = $selectedDatabaseId ?? $page.params.database_id;
			return activeDb ? `/metadata/${activeDb}/documentation` : href;
		}
		if (href === '/metadata/tag') {
			const activeServer = $selectedServerId;
			return activeServer ? `/metadata/${activeServer}/tag` : href;
		}
		return href;
	}

	$effect(() => {
		const routeDbId = $page.params.database_id;
		const currentPath = $page.url.pathname;

		if (routeDbId) {
			selectedDatabaseId.set(routeDbId);
		}

		if (isActive('/analytics', currentPath)) expandedAnalytics = true;
		if (isActive('/alerts', currentPath)) expandedAlerts = true;
		if (isActive('/runs', currentPath)) expandedRuns = true;
		if (/^\/runs\/[^/]+\/settings\/(server|database)/.test(currentPath))
			expandedRunsSettings = true;
		if (isActive('/metadata', currentPath)) expandedMetadata = true;
		if (isActive('/settings', currentPath)) expandedSettings = true;
	});

	$effect(() => {
		const databaseId = $page.params.database_id;
		const serverId = $page.params.server_id;
		const key = `${databaseId ?? ''}:${serverId ?? ''}`;
		if (authState !== 'authenticated' || (!databaseId && !serverId) || key === checkedRoute) return;
		checkedRoute = key;
		void validateRouteTarget(databaseId, serverId);
	});

	$effect(() => {
		$page.url.pathname;
		if (authState === 'authenticated' && Date.now() - lastValidatedAt > 15_000) {
			void checkSession();
		}
	});

	async function validateRouteTarget(databaseId?: string, serverId?: string) {
		try {
			if (databaseId) {
				const databases = await listDatabases();
				if (
					$page.params.database_id !== databaseId ||
					databases.some((item) => item.id === databaseId)
				)
					return;
				showRouteError('This database no longer exists or is no longer available.');
				await goto('/search', { replaceState: true });
				return;
			}

			if (serverId) {
				const servers = await listServers();
				if ($page.params.server_id !== serverId || servers.some((item) => item.id === serverId))
					return;
				showRouteError('This server no longer exists or is no longer available.');
				await goto('/search', { replaceState: true });
			}
		} catch {
			// Individual pages retain their existing request errors when the resource list is unavailable.
		}
	}

	function showRouteError(message: string) {
		routeError = message;
		if (routeErrorTimeout) window.clearTimeout(routeErrorTimeout);
		routeErrorTimeout = window.setTimeout(() => (routeError = ''), 6000);
	}

	function isActive(href: string, currentPath: string) {
		return currentPath === href || currentPath.startsWith(`${href}/`);
	}

	function normalizeSubmenuPath(path: string) {
		const segments = path.split('/').filter(Boolean);
		const section = segments[0];

		if ((section === 'analytics' || section === 'runs') && segments.length >= 3) {
			return `/${section}/${segments.slice(2).join('/')}`;
		}

		if (section === 'metadata' && segments.length >= 3) {
			return `/metadata/${segments[2]}`;
		}

		return path;
	}

	function isSubmenuActive(href: string, currentPath: string) {
		return isActive(href, normalizeSubmenuPath(currentPath));
	}

	function resolveRunSettingsHref(item: (typeof runSettingsItems)[number]) {
		if (item.idType === 'services') return item.href;
		const id = item.idType === 'server' ? $selectedServerId : $selectedDatabaseId;
		return id ? `${item.href}/${id}${item.suffix}` : `${item.href}${item.suffix}`;
	}

	function isRunSettingsActive(item: (typeof runSettingsItems)[number], currentPath: string) {
		if (item.idType === 'services') return currentPath === item.href;
		const pattern = new RegExp(`^${item.href}/[^/]+${item.suffix}(/.*)?$`);
		return pattern.test(currentPath);
	}

	let collapsed = $state(
		typeof localStorage !== 'undefined' && localStorage.getItem('sidebar_collapsed') === 'true'
	);

	function toggleSidebar() {
		collapsed = !collapsed;
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem('sidebar_collapsed', String(collapsed));
		}
	}

	function toggleNotifications() {
		notificationsOpen = !notificationsOpen;
	}
</script>

{#if authState === 'authenticated'}
	<div
		class="bg-background text-on-background selection:bg-primary-container selection:text-on-primary-container min-h-screen"
	>
		<aside
			class="h-screen fixed left-0 top-0 bg-background border-r border-surface-border flex flex-col z-40 transition-[width] duration-300 ease-in-out {collapsed
				? 'w-16'
				: 'w-64'}"
		>
			<div class="p-4 flex items-center {collapsed ? 'flex-col gap-2' : 'gap-3'}">
				<img
					src="/branding/logo.jpg"
					alt="pgwarden logo"
					class="w-8 h-8 rounded object-cover shrink-0"
				/>
				{#if !collapsed}
					<span class="font-headline-md min-w-0 flex-1 text-primary font-bold tracking-tight"
						>pgwarden</span
					>
				{/if}
				<button
					type="button"
					onclick={toggleNotifications}
					class="group relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition-all hover:-translate-y-px hover:bg-surface-panel hover:text-primary {notificationsOpen
						? 'border-primary bg-primary/10 text-primary'
						: 'border-transparent text-on-surface-variant'}"
					aria-label="Toggle notifications"
					aria-expanded={notificationsOpen}
					title="Notifications"
				>
					<span
						class="material-symbols-outlined text-[20px] transition-transform group-hover:rotate-12"
						style={notificationsOpen ? "font-variation-settings: 'FILL' 1;" : ''}
						>notifications</span
					>
					{#if notificationCount > 0}
						<span
							class="absolute -right-1.5 -top-1.5 flex min-w-4 h-4 items-center justify-center rounded-full bg-status-danger px-1 text-[9px] font-bold leading-none text-white ring-2 ring-background"
						>
							{notificationCount > 99 ? '99+' : notificationCount}
						</span>
					{/if}
				</button>
			</div>

			{#if !collapsed}
				<div
					class="px-4 py-2 font-label-caps text-on-surface-variant uppercase tracking-wider text-xs"
				>
					Menu
				</div>
			{/if}

			<nav class="flex-1 px-2 space-y-1 overflow-y-auto overflow-x-hidden custom-scrollbar">
				{#each navItems as item}
					{@const href = resolveHref(item.href, item.needsDb, $page.params.database_id ?? null)}
					{@const active = isActive(item.href, $page.url.pathname)}
					<a
						{href}
						title={collapsed ? item.name : undefined}
						class="sidebar-item font-body-sm text-on-surface {collapsed
							? 'justify-center'
							: ''} {active ? 'active' : ''}"
					>
						<span
							class="material-symbols-outlined text-lg"
							style={active ? "font-variation-settings: 'FILL' 1;" : ''}>{item.icon}</span
						>
						{#if !collapsed}<span>{item.name}</span>{/if}
					</a>
				{/each}

				{#if !collapsed}
					<div class="mt-2">
						<button
							onclick={() => (expandedAlerts = !expandedAlerts)}
							class="sidebar-item font-body-sm text-on-surface justify-between w-full"
						>
							<div class="flex items-center gap-3">
								<span class="material-symbols-outlined text-lg">notifications</span>
								<span>Alerts</span>
							</div>
							<span class="material-symbols-outlined text-sm"
								>{expandedAlerts ? 'expand_less' : 'expand_more'}</span
							>
						</button>
						{#if expandedAlerts}
							<div class="space-y-1 mt-1">
								{#each alertsItems as item}
									{@const active = isActive(item.href, $page.url.pathname)}
									<a
										href={active ? $page.url.pathname : item.href}
										aria-current={active ? 'page' : undefined}
										class="sidebar-item sidebar-nested font-body-sm text-on-surface-variant {active
											? 'active'
											: ''}"
									>
										<span
											class="material-symbols-outlined text-base"
											style={active ? "font-variation-settings: 'FILL' 1;" : ''}>{item.icon}</span
										>
										<span>{item.name}</span>
									</a>
								{/each}
							</div>
						{/if}
					</div>
					<div class="mt-2">
						<button
							onclick={() => (expandedAnalytics = !expandedAnalytics)}
							class="sidebar-item font-body-sm text-on-surface justify-between w-full"
						>
							<div class="flex items-center gap-3">
								<span class="material-symbols-outlined text-lg">analytics</span>
								<span>Analytics</span>
							</div>
							<span class="material-symbols-outlined text-sm"
								>{expandedAnalytics ? 'expand_less' : 'expand_more'}</span
							>
						</button>
						{#if expandedAnalytics}
							<div class="space-y-1 mt-1">
								{#each analyticsItems as item}
									{@const href = resolveHref(
										item.href,
										item.needsDb,
										$page.params.database_id ?? null
									)}
									{@const active = isSubmenuActive(item.href, $page.url.pathname)}
									<a
										href={active ? $page.url.pathname : href}
										aria-current={active ? 'page' : undefined}
										class="sidebar-item sidebar-nested font-body-sm text-on-surface-variant {active
											? 'active'
											: ''}"
									>
										<span
											class="material-symbols-outlined text-base"
											style={active ? "font-variation-settings: 'FILL' 1;" : ''}>{item.icon}</span
										>
										<span>{item.name}</span>
									</a>
								{/each}
							</div>
						{/if}
					</div>

					<div class="mt-2">
						<button
							onclick={() => (expandedRuns = !expandedRuns)}
							class="sidebar-item font-body-sm text-on-surface justify-between w-full"
						>
							<div class="flex items-center gap-3">
								<span class="material-symbols-outlined text-lg">play_arrow</span>
								<span>Runs</span>
							</div>
							<span class="material-symbols-outlined text-sm"
								>{expandedRuns ? 'expand_less' : 'expand_more'}</span
							>
						</button>
						{#if expandedRuns}
							<div class="space-y-1 mt-1">
								{#each runItems as item}
									{@const href = resolveHref(
										item.href,
										item.needsDb,
										$page.params.database_id ?? null
									)}
									{@const active = isSubmenuActive(item.href, $page.url.pathname)}
									<a
										href={active ? $page.url.pathname : href}
										aria-current={active ? 'page' : undefined}
										class="sidebar-item sidebar-nested font-body-sm text-on-surface-variant {active
											? 'active'
											: ''}"
									>
										<span
											class="material-symbols-outlined text-base"
											style={active ? "font-variation-settings: 'FILL' 1;" : ''}>{item.icon}</span
										>
										<span>{item.name}</span>
									</a>
								{/each}

								<div class="space-y-1">
									<button
										onclick={() => (expandedRunsSettings = !expandedRunsSettings)}
										class="sidebar-item sidebar-nested font-body-sm text-on-surface-variant justify-between w-full"
									>
										<div class="flex items-center gap-3">
											<span class="material-symbols-outlined text-base">settings</span>
											<span>Settings</span>
										</div>
										<span class="material-symbols-outlined text-sm"
											>{expandedRunsSettings ? 'expand_less' : 'expand_more'}</span
										>
									</button>
									{#if expandedRunsSettings}
										<div class="space-y-1 mt-1">
											{#each runSettingsItems as item}
												{@const href = resolveRunSettingsHref(item)}
												{@const active = isRunSettingsActive(item, $page.url.pathname)}
												<a
													href={active ? $page.url.pathname : href}
													aria-current={active ? 'page' : undefined}
													class="sidebar-item sidebar-nested font-body-sm text-on-surface-variant {active
														? 'active'
														: ''}"
												>
													<span
														class="material-symbols-outlined text-base"
														style={active ? "font-variation-settings: 'FILL' 1;" : ''}
														>{item.icon}</span
													>
													<span>{item.name}</span>
												</a>
											{/each}
										</div>
									{/if}
								</div>
							</div>
						{/if}
					</div>
					<div class="mt-2">
						<button
							onclick={() => (expandedMetadata = !expandedMetadata)}
							class="sidebar-item font-body-sm text-on-surface justify-between w-full"
						>
							<div class="flex items-center gap-3">
								<span class="material-symbols-outlined text-lg">folder_managed</span>
								<span>Metadata</span>
							</div>
							<span class="material-symbols-outlined text-sm"
								>{expandedMetadata ? 'expand_less' : 'expand_more'}</span
							>
						</button>
						{#if expandedMetadata}
							<div class="space-y-1 mt-1">
								{#each metadataItems as item}
									{@const href = resolveMetadataHref(item.href)}
									{@const active = isSubmenuActive(item.href, $page.url.pathname)}
									<a
										href={active ? $page.url.pathname : href}
										aria-current={active ? 'page' : undefined}
										class="sidebar-item sidebar-nested font-body-sm text-on-surface-variant {active
											? 'active'
											: ''}"
									>
										<span
											class="material-symbols-outlined text-base"
											style={active ? "font-variation-settings: 'FILL' 1;" : ''}>{item.icon}</span
										>
										<span>{item.name}</span>
									</a>
								{/each}
							</div>
						{/if}
					</div>

					<div class="mt-2">
						<button
							onclick={() => (expandedSettings = !expandedSettings)}
							class="sidebar-item font-body-sm text-on-surface justify-between w-full"
						>
							<div class="flex items-center gap-3">
								<span class="material-symbols-outlined text-lg">settings</span>
								<span>Settings</span>
							</div>
							<span class="material-symbols-outlined text-sm"
								>{expandedSettings ? 'expand_less' : 'expand_more'}</span
							>
						</button>
						{#if expandedSettings}
							<div class="space-y-1 mt-1">
								{#each settingsItems as item}
									{@const href = resolveHref(
										item.href,
										item.needsDb,
										$page.params.database_id ?? null
									)}
									{@const active = isSubmenuActive(item.href, $page.url.pathname)}
									<a
										href={active ? $page.url.pathname : href}
										aria-current={active ? 'page' : undefined}
										class="sidebar-item sidebar-nested font-body-sm text-on-surface-variant {active
											? 'active'
											: ''}"
									>
										<span
											class="material-symbols-outlined text-base"
											style={active ? "font-variation-settings: 'FILL' 1;" : ''}>{item.icon}</span
										>
										<span>{item.name}</span>
									</a>
								{/each}
							</div>
						{/if}
					</div>
				{/if}
			</nav>

			<div class="border-t border-surface-border p-4 mt-auto">
				<div
					class="flex items-center {collapsed
						? 'justify-center'
						: 'justify-between'} cursor-pointer hover:bg-surface-panel p-2 -mx-2 rounded transition-colors"
				>
					<div class="flex items-center {collapsed ? '' : 'gap-3'}">
						<div
							class="w-8 h-8 rounded-full bg-primary-container text-on-primary-container flex items-center justify-center font-bold text-xs shrink-0"
						>
							DBA
						</div>
						{#if !collapsed}
							<div class="flex flex-col">
								<span class="font-body-sm text-on-surface font-semibold">admin</span>
								<span class="text-[10px] text-on-surface-variant">Session Active</span>
							</div>
						{/if}
					</div>
					{#if !collapsed}
						<button
							onclick={redirectToLogin}
							class="text-on-surface-variant hover:text-error transition-colors"
							title="Logout"
						>
							<span class="material-symbols-outlined text-[20px]">logout</span>
						</button>
					{/if}
				</div>
			</div>
		</aside>

		<!-- Collapse / expand toggle button (root-level fixed so it always paints
	     above the page headers, which sit at the sidebar's right edge) -->
		<button
			onclick={toggleSidebar}
			title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
			aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
			class="fixed top-6 z-50 w-6 h-6 rounded-full bg-surface-container-high border border-surface-border flex items-center justify-center text-on-surface-variant hover:bg-primary hover:text-on-primary hover:border-primary transition-[left] duration-300 ease-in-out shrink-0"
			style:left={collapsed ? '3.25rem' : '15.25rem'}
		>
			<span class="material-symbols-outlined text-[16px] leading-none"
				>{collapsed ? 'chevron_right' : 'chevron_left'}</span
			>
		</button>

		<NotificationPanel
			open={notificationsOpen}
			{collapsed}
			onClose={() => (notificationsOpen = false)}
			onCountChange={(count) => (notificationCount = count)}
		/>

		<main
			class="min-h-screen transition-[margin] duration-300 ease-in-out"
			style:margin-left={collapsed
				? notificationsOpen
					? '28rem'
					: '4rem'
				: notificationsOpen
					? '40rem'
					: '16rem'}
		>
			{#if routeError}
				<div
					class="fixed top-4 z-[60] flex w-[min(32rem,calc(100vw-2rem))] items-center gap-3 rounded-lg border border-error/30 bg-error-container px-4 py-3 text-sm text-on-error-container shadow-lg"
					style:left={collapsed ? 'calc(4rem + 1rem)' : 'calc(16rem + 1rem)'}
					role="alert"
				>
					<span class="material-symbols-outlined text-[20px]">error</span>
					<span class="flex-1">{routeError}</span>
					<button
						onclick={() => (routeError = '')}
						class="rounded p-0.5 hover:bg-error/10"
						aria-label="Dismiss error"
						><span class="material-symbols-outlined text-[18px]">close</span></button
					>
				</div>
			{/if}
			{@render children()}
		</main>
	</div>
{:else}
	<div class="flex min-h-screen items-center justify-center bg-background px-6 text-on-background">
		<div class="max-w-sm text-center">
			{#if authState === 'checking'}
				<span class="material-symbols-outlined animate-spin text-4xl text-primary"
					>progress_activity</span
				>
				<p class="mt-3 text-sm text-on-surface-variant">Validating your session…</p>
			{:else}
				<span class="material-symbols-outlined text-4xl text-error">cloud_off</span>
				<h1 class="mt-3 text-lg font-bold text-on-surface">Unable to validate your session</h1>
				<p class="mt-2 text-sm text-on-surface-variant">
					The API is currently unavailable. Check the service and try again.
				</p>
				<button
					onclick={() => checkSession(true)}
					class="mt-5 rounded-lg bg-primary px-4 py-2 text-sm font-bold text-on-primary"
				>
					Try again
				</button>
			{/if}
		</div>
	</div>
{/if}
