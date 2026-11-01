<script lang="ts">
	import Select from '$lib/components/Select.svelte';
	import Spinner from '$lib/components/Spinner.svelte';
	import { resolve } from '$app/paths';
	import { onMount, tick } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { redirectToLogin, validateSession } from '$lib/auth';
	import { profile, can, canVisit, loadProfile } from '$lib/access';
	import NotificationPanel from '$lib/components/NotificationPanel.svelte';
	import { listDatabases, listServers } from '$lib/api';
	import type { DatabaseListItem, ServerListItem } from '$lib/api';
	import { selectedDatabaseId } from '$lib/stores/selectedDatabase';
	import { selectedServerId } from '$lib/stores/selectedServer';
	import {
		contextualHref,
		destinations,
		sectionFor,
		sectionTabs,
		tabIsActive,
		switchDatabasePath,
		switchServerPath,
		workspaceContext
	} from '$lib/navigation';
	let { children } = $props();
	let databases = $state<DatabaseListItem[]>([]);
	let servers = $state<ServerListItem[]>([]);
	let catalogError = $state('');
	let mobileOpen = $state(false);
	let collapsed = $state(false);
	let sidebarElement = $state<HTMLElement>();
	let menuButton = $state<HTMLButtonElement>();
	const section = $derived(sectionFor($page.url.pathname));
	const tabs = $derived((sectionTabs[section] ?? []).filter(tab => canVisit($profile, tab.href)));
	const context = $derived(
		workspaceContext(
			databases,
			$page.params.database_id,
			$page.params.server_id,
			$selectedDatabaseId,
			$selectedServerId
		)
	);
	const currentDatabase = $derived(context.databaseId);
	const currentServer = $derived(context.serverId);
	const availableDatabases = $derived(
		currentServer ? databases.filter((db) => db.server_id === currentServer) : databases
	);
	let notificationsOpen = $state(false);
	let notificationCount = $state(0);
	let routeError = $state('');
	let checkedRoute = $state('');
	let routeErrorTimeout: number | null = null;
	let authState = $state<'checking' | 'authenticated' | 'unavailable'>('checking');
	let lastValidatedAt = 0;
	let validating = false;

	async function checkSession(blockPage = false) {
		if (validating) return;
		validating = true;
		if (blockPage) authState = 'checking';
		const result = await validateSession();
		validating = false;
		if (result === 'valid') {
			try { await loadProfile(); } catch { authState = 'unavailable'; return; }
			lastValidatedAt = Date.now();
			authState = 'authenticated';
		} else if (result === 'unavailable' && authState !== 'authenticated') {
			authState = 'unavailable';
		}
	}

	onMount(() => {
		void checkSession(true);
		const interval = window.setInterval(() => {
			if (document.visibilityState === 'visible') void checkSession();
		}, 60_000);
		const validateActiveSession = () => {
			if (document.visibilityState === 'visible' && Date.now() - lastValidatedAt > 15_000)
				void checkSession();
		};
		window.addEventListener('pgwarden:catalog-invalidated', loadCatalog);
		window.addEventListener('focus', validateActiveSession);
		document.addEventListener('visibilitychange', validateActiveSession);
		return () => {
			window.clearInterval(interval);
			window.removeEventListener('pgwarden:catalog-invalidated', loadCatalog);
			window.removeEventListener('focus', validateActiveSession);
			document.removeEventListener('visibilitychange', validateActiveSession);
		};
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
				await goto(resolve('/search'), { replaceState: true });
				return;
			}

			if (serverId) {
				const servers = await listServers();
				if ($page.params.server_id !== serverId || servers.some((item) => item.id === serverId))
					return;
				showRouteError('This server no longer exists or is no longer available.');
				await goto(resolve('/search'), { replaceState: true });
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

	let catalogSequence = 0;
	async function loadCatalog() {
		const sequence = ++catalogSequence;
		try {
			const catalog = await Promise.all([listDatabases(), listServers()]);
			if (sequence !== catalogSequence) return;
			[databases, servers] = catalog;
			catalogError = '';
		} catch {
			if (sequence !== catalogSequence) return;
			catalogError = 'Context unavailable';
		}
	}
	function href(path: string) {
		if (path === '/settings/connections' && !$profile?.is_admin) return '/settings/servers';
		return contextualHref(path, currentDatabase, currentServer);
	}
	function changeDatabase(id: string) {
		selectedDatabaseId.set(id);
		const serverId = databases.find((db) => db.id === id)?.server_id ?? null;
		selectedServerId.set(serverId);
		const databasePath = switchDatabasePath($page.url.pathname, id);
		void goto(
			resolve(
				...([serverId ? switchServerPath(databasePath, serverId) : databasePath] as Parameters<
					typeof resolve
				>)
			)
		);
	}
	function changeServer(id: string) {
		selectedServerId.set(id);
		const database = databases.find((db) => db.server_id === id);
		if (database) changeDatabase(database.id);
		else {
			selectedDatabaseId.set(null);
			const serverPath = switchServerPath($page.url.pathname, id);
			void goto(
				resolve(
					...([serverPath !== $page.url.pathname ? serverPath : '/settings/servers'] as Parameters<
						typeof resolve
					>)
				)
			);
		}
	}
	function toggleSidebar() {
		collapsed = !collapsed;
		localStorage.setItem('sidebar_collapsed', String(collapsed));
	}
	function closeMenu() {
		mobileOpen = false;
		menuButton?.focus();
	}
	async function openMenu() {
		notificationsOpen = false;
		mobileOpen = true;
		await tick();
		sidebarElement?.querySelector('a')?.focus();
	}
	function handleKey(event: KeyboardEvent) {
		if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
			event.preventDefault();
			void goto(resolve('/search'));
		}
		if (event.key === 'Escape') {
			notificationsOpen = false;
			if (mobileOpen) closeMenu();
		}
		if (event.key === 'Tab' && mobileOpen) {
			const items = [...(sidebarElement?.querySelectorAll<HTMLElement>('a, button') ?? [])].filter(
				(el) => el.getClientRects().length
			);
			const first = items[0],
				last = items.at(-1);
			if (event.shiftKey && document.activeElement === first) {
				event.preventDefault();
				last?.focus();
			} else if (!event.shiftKey && document.activeElement === last) {
				event.preventDefault();
				first?.focus();
			}
		}
	}
	onMount(() => {
		collapsed = localStorage.getItem('sidebar_collapsed') === 'true';
		return () => {
			if (routeErrorTimeout) window.clearTimeout(routeErrorTimeout);
		};
	});
	$effect(() => {
		if (authState === 'authenticated') void loadCatalog();
	});
	$effect(() => {
		void $page.url.pathname;
		mobileOpen = false;
		if ($page.params.database_id) selectedDatabaseId.set($page.params.database_id);
		if ($page.params.server_id) selectedServerId.set($page.params.server_id);
	});
	$effect(() => {
		const databaseId = $page.params.database_id,
			serverId = $page.params.server_id;
		const key = (databaseId ?? '') + ':' + (serverId ?? '') + ':' + JSON.stringify([$profile?.server_ids, $profile?.database_ids]);
		if (authState !== 'authenticated' || (!databaseId && !serverId) || key === checkedRoute) return;
		checkedRoute = key;
		void validateRouteTarget(databaseId, serverId);
	});
</script>

<svelte:window onkeydown={handleKey} />
{#if authState === 'authenticated'}
	<div
		class="app-shell"
		class:sidebar-collapsed={collapsed}
		class:mobile-open={mobileOpen}
		style:--sidebar-width={collapsed ? '4rem' : '15rem'}
	>
		<a class="skip-link" href="#main-content">Skip to content</a>
		{#if mobileOpen}<button class="nav-backdrop" aria-label="Close navigation" onclick={closeMenu}
			></button>{/if}
		<aside class="app-sidebar" bind:this={sidebarElement} aria-label="Main navigation">
			<div class="sidebar-header">
				<a href={resolve('/overview')} class="app-brand" aria-label="PGWarden overview"
					><img src="/branding/logo.jpg" alt="" width="28" height="28" /><span class="sidebar-label"
						>pgwarden <small>POSTGRES OBSERVABILITY</small></span
					></a
				>
				<button
					type="button"
					class="sidebar-collapse desktop-collapse"
					onclick={toggleSidebar}
					aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
					title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
					aria-expanded={!collapsed}
					aria-controls="primary-navigation"
				>
					<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"
						><path
							d="m14 6-6 6 6 6"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
						/></svg
					>
				</button>
			</div>
			<button
				class="sidebar-search sidebar-item"
				onclick={() => {
					mobileOpen = false;
					void goto(resolve('/search'));
				}}
				title="Search (Ctrl+K)"
				aria-label="Search (Ctrl+K)"
				><span class="material-symbols-outlined">search</span><span class="sidebar-label"
					>Search</span
				><kbd class="sidebar-label">Ctrl K</kbd></button
			>
			<div class="nav-caption sidebar-label">WORKSPACE</div>
			<nav id="primary-navigation" class="primary-navigation">
				{#each destinations.filter(item => canVisit($profile, href(item.href))) as item (item.href)}
					{@const active = section === sectionFor(item.href)}
					<a
						href={resolve(...([href(item.href)] as Parameters<typeof resolve>))}
						class="sidebar-item"
						class:active
						aria-current={active ? 'page' : undefined}
						aria-label={item.label}
						title={item.label}
						><span class="material-symbols-outlined">{item.icon}</span><span class="sidebar-label"
							>{item.label}</span
						></a
					>
				{/each}
			</nav>
			<div class="sidebar-footer">
				<button class="sidebar-item mobile-close" onclick={closeMenu}
					><span class="material-symbols-outlined">close</span>Close navigation</button
				>
				<button
					class="sidebar-item"
					onclick={redirectToLogin}
					aria-label="Sign out"
					title="Sign out"
					><span class="material-symbols-outlined">logout</span><span class="sidebar-label"
						>Sign out</span
					></button
				>
			</div>
		</aside>
		<div class="workspace-toolbar">
			<button
				class="icon-button mobile-menu"
				bind:this={menuButton}
				onclick={openMenu}
				aria-label="Open navigation"
				aria-expanded={mobileOpen}><span class="material-symbols-outlined">menu</span></button
			>
			<div class="context-select">
				<span class="material-symbols-outlined">dns</span><Select
					aria-label="Server"
					value={currentServer ?? ''}
					onchange={(value) => changeServer(value)}
					options={[
						{ value: '', label: 'Select server', disabled: true },
						...servers.map((item) => ({ value: item.id, label: item.name }))
					]}
				/>
			</div>
			<span class="context-divider">/</span>
			<div class="context-select">
				<span class="material-symbols-outlined">database</span><Select
					aria-label="Database"
					value={currentDatabase ?? ''}
					onchange={(value) => changeDatabase(value)}
					options={[
						{ value: '', label: 'Select database', disabled: true },
						...availableDatabases.map((item) => ({ value: item.id, label: item.name }))
					]}
				/>
			</div>
			{#if catalogError}<button class="context-retry" onclick={loadCatalog}
					>{catalogError} · Retry</button
				>{/if}
			<button
				disabled={!can($profile, 'alerts.read')}
				class="icon-button notification-toggle"
				onclick={() => (notificationsOpen = !notificationsOpen)}
				aria-label={notificationCount
					? 'Notifications, ' + notificationCount + ' active'
					: 'Notifications'}
				aria-expanded={notificationsOpen}
				><span class="material-symbols-outlined">notifications</span
				>{#if notificationCount > 0}<span class="notification-dot"></span>{/if}</button
			>
		</div>
		{#if tabs.length}<nav class="section-tabs" aria-label="Section navigation">
				{#each tabs as tab (tab.href)}{@const target = href(tab.href)}<a
						href={resolve(...([target] as Parameters<typeof resolve>))}
						aria-current={tabIsActive($page.url.pathname, target) ? 'page' : undefined}
						>{tab.label}</a
					>{/each}
			</nav>{/if}
		{#if can($profile, 'alerts.read')}<NotificationPanel
			open={notificationsOpen}
			onClose={() => (notificationsOpen = false)}
			onCountChange={(count) => (notificationCount = count)}
		/>{/if}
		<main id="main-content" class="workspace-content" tabindex="-1" inert={mobileOpen}>
			{#if routeError}<div class="route-error" role="alert">
					<span>{routeError}</span><button
						onclick={() => (routeError = '')}
						aria-label="Dismiss error">×</button
					>
				</div>{/if}
			{#if !canVisit($profile, $page.url.pathname)}<div role="alert" class="route-error">You do not have permission to view this page.</div>{:else}
			{#key ($page.params.database_id ?? '') + ':' + ($page.params.server_id ?? '')}{@render children()}{/key}{/if}
		</main>
	</div>
{:else}
	<div class="flex min-h-screen items-center justify-center bg-background px-6 text-on-background">
		<div class="max-w-sm text-center">
			{#if authState === 'checking'}
				<Spinner class="text-4xl text-primary" />
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
