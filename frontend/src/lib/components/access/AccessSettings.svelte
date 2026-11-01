<script lang="ts">
	import { onMount } from 'svelte';
	import { accessApi, type Role, type ManagedUser } from '$lib/access';
	import { listDatabases, listServers, type DatabaseListItem, type ServerListItem } from '$lib/api';
	import { listProjects } from '$lib/projects-api';
	let { mode }: { mode: 'users' | 'roles' } = $props();
	let generatedPassword = $state('');
	let credentialEmail = $state('');
	let copied = $state(false);

	let roles = $state<Role[]>([]);
	let users = $state<ManagedUser[]>([]);
	let projects = $state<{ id: string; name: string }[]>([]);
	let servers = $state<(ServerListItem & { project_id?: string | null })[]>([]);
	let databases = $state<DatabaseListItem[]>([]);
	let roleId = $state<number | null>(null);
	let roleName = $state('');
	let permissions = $state<string[]>([]);
	let projectIds = $state<string[]>([]);
	let serverIds = $state<string[]>([]);
	let databaseIds = $state<string[]>([]);
	let userId = $state<number | null>(null);
	let name = $state('');
	let email = $state('');
	let isAdmin = $state(false);
	let userRole = $state<number | null>(null);
	let busy = $state(false);
	let loading = $state(true);
	let error = $state('');
	let notice = $state('');
	const features = [
		{ key: 'alerts', name: 'Alerts' },
		{ key: 'documentation', name: 'Documentation' },
		{ key: 'schedulers', name: 'Schedulers' }
	];
	const eligibleServers = $derived(
		servers.filter((s) => !s.project_id || projectIds.includes(s.project_id))
	);
	const eligibleDatabases = $derived(databases.filter((d) => serverIds.includes(d.server_id)));

	async function load() {
		[roles, users, projects, servers, databases] = await Promise.all([
			accessApi<Role[]>('roles'),
			mode === 'users' ? accessApi<ManagedUser[]>('users') : Promise.resolve([]),
			mode === 'roles' ? listProjects() : Promise.resolve([]),
			mode === 'roles' ? listServers() : Promise.resolve([]),
			mode === 'roles' ? listDatabases() : Promise.resolve([])
		]);
	}
	function editRole(role?: Role) {
		roleId = role?.id ?? null;
		roleName = role?.name ?? '';
		permissions = [...(role?.permissions ?? [])];
		projectIds = [...(role?.project_ids ?? [])];
		serverIds = [...(role?.server_ids ?? [])];
		databaseIds = [...(role?.database_ids ?? [])];
	}
	function editUser(user?: ManagedUser) {
		userId = user?.id ?? null;
		name = user?.name ?? '';
		email = user?.email ?? '';
		generatedPassword = '';
		copied = false;
		isAdmin = user?.is_admin ?? false;
		userRole = user?.role_id ?? null;
	}
	function pruneChildren() {
		serverIds = serverIds.filter((id) => eligibleServers.some((s) => s.id === id));
		databaseIds = databaseIds.filter((id) =>
			databases.some((d) => d.id === id && serverIds.includes(d.server_id))
		);
	}
	async function perform(action: () => Promise<void>) {
		busy = true;
		error = '';
		notice = '';
		try {
			await action();
			await load();
			notice = 'Changes saved.';
		} catch (cause) {
			error = cause instanceof Error ? cause.message : 'Could not save changes.';
		} finally {
			busy = false;
		}
	}
	async function saveRole(event: SubmitEvent) {
		event.preventDefault();
		await perform(async () => {
			pruneChildren();
			await accessApi(roleId ? `roles/${roleId}` : 'roles', roleId ? 'PUT' : 'POST', {
				name: roleName,
				permissions,
				project_ids: projectIds,
				server_ids: serverIds,
				database_ids: databaseIds
			});
			editRole();
		});
	}
	async function saveUser(event: SubmitEvent) {
		event.preventDefault();
		await perform(async () => {
			const creating = userId === null;
			const saved = await accessApi<ManagedUser & { generated_password?: string }>(
				userId ? `users/${userId}` : 'users',
				userId ? 'PUT' : 'POST',
				{
					name,
					email,
					is_admin: isAdmin,
					role_id: isAdmin ? null : userRole
				}
			);
			editUser();
			if (creating && saved.generated_password) {
				generatedPassword = saved.generated_password;
				credentialEmail = saved.email;
			}
		});
	}
	async function remove(kind: 'users' | 'roles', id: number) {
		if (!window.confirm(`Delete this ${kind === 'users' ? 'user' : 'role'}?`)) return;
		await perform(async () => {
			await accessApi(`${kind}/${id}`, 'DELETE');
			editRole();
			editUser();
		});
	}
	onMount(async () => {
		try {
			await load();
		} catch (cause) {
			error = String(cause);
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head><title>{mode === 'users' ? 'Users' : 'Roles'} · PGWarden</title></svelte:head>
<div class="access-page">
	<header>
		<h1>{mode === 'users' ? 'Users' : 'Roles'}</h1>
		<p>Administrators have full access. Each other user has one role.</p>
	</header>
	{#if error}<p class="message error" role="alert">{error}</p>{/if}
	{#if notice}<p class="message" role="status">{notice}</p>{/if}
	{#if generatedPassword}<div class="message" role="status">
			<p>Initial password for {credentialEmail}. Copy it now; it will not be shown again.</p>
			<code class="credential">{generatedPassword}</code><button
				onclick={async () => {
					try {
						await navigator.clipboard.writeText(generatedPassword);
						copied = true;
					} catch {
						error = 'Could not copy. Select and copy the password manually.';
					}
				}}>{copied ? 'Copied' : 'Copy password'}</button
			><button onclick={() => (generatedPassword = '')}>Dismiss</button>
		</div>{/if}
	{#if loading}<p>Loading access settings…</p>{:else}
		<div class="columns">
			{#if mode === 'roles'}<section>
					<div class="heading">
						<h2>Roles</h2>
						<button onclick={() => editRole()}>New role</button>
					</div>
					{#each roles as role (role.id)}
						<div class="list-row">
							<button class="name" onclick={() => editRole(role)}>{role.name}</button><button
								disabled={busy}
								onclick={() => remove('roles', role.id)}>Delete</button
							>
						</div>
					{:else}<p>No roles yet.</p>{/each}
					<form onsubmit={saveRole}>
						<fieldset disabled={busy}>
							<legend>{roleId ? 'Edit role' : 'Create role'}</legend>
							<label>Role name<input required maxlength="100" bind:value={roleName} /></label>
							<table>
								<thead><tr><th>Permission</th><th>Read</th><th>Configure</th></tr></thead><tbody>
									{#each features as feature}
										<tr
											><th>{feature.name}</th>
											{#each ['read', 'configure'] as mode}<td
													><input
														type="checkbox" role="switch"
														aria-label={`${feature.name}: ${mode}`}
														value={`${feature.key}.${mode}`}
														bind:group={permissions}
													/></td
												>{/each}
										</tr>
									{/each}
								</tbody>
							</table>
							<p>
								Select each resource explicitly. A database also requires its server and project.
							</p>
							<h3>Projects</h3>
							{#each projects as project}<label class="choice"
									><input
										type="checkbox" role="switch"
										value={project.id}
										bind:group={projectIds}
										onchange={() => queueMicrotask(pruneChildren)}
									/>{project.name}</label
								>{:else}<p>No projects.</p>{/each}
							<h3>Servers</h3>
							{#each eligibleServers as server}<label class="choice"
									><input
										type="checkbox" role="switch"
										value={server.id}
										bind:group={serverIds}
										onchange={() => queueMicrotask(pruneChildren)}
									/>{server.name}</label
								>{:else}<p>Select a project to see its servers.</p>{/each}
							<h3>Databases</h3>
							{#each eligibleDatabases as database}<label class="choice"
									><input
										type="checkbox" role="switch"
										value={database.id}
										bind:group={databaseIds}
									/>{servers.find((s) => s.id === database.server_id)?.name} / {database.name}</label
								>{:else}<p>Select a server to see its databases.</p>{/each}
							<button class="primary" type="submit">Save role</button>
						</fieldset>
					</form>
				</section>{:else}
				<section>
					<div class="heading">
						<h2>Users</h2>
						<button onclick={() => editUser()}>New user</button>
					</div>
					{#each users as user (user.id)}
						<div class="list-row">
							<button class="name" onclick={() => editUser(user)}
								>{user.name}<small
									>{user.email} · {user.is_admin
										? 'Administrator'
										: (roles.find((r) => r.id === user.role_id)?.name ?? 'No role')}</small
								></button
							><button disabled={busy} onclick={() => remove('users', user.id)}>Delete</button>
						</div>
					{/each}
					<form onsubmit={saveUser}>
						<fieldset disabled={busy}>
							<legend>{userId ? 'Edit user' : 'Create user'}</legend>
							<label
								>Name<input required maxlength="50" bind:value={name} autocomplete="name" /></label
							>
							<label
								>Email<input
									required
									type="email"
									maxlength="100"
									bind:value={email}
									autocomplete="off"
								/></label
							>
							{#if !userId}<p>
									An 8-character password with letters, numbers, and symbols is generated when you
									create the user. It is shown once after saving.
								</p>{/if}
							<label class="choice"
								><input type="checkbox" role="switch" bind:checked={isAdmin} />Administrator — full access</label
							>
							{#if !isAdmin}<label
									>Role<select required bind:value={userRole}
										><option value={null} disabled>Select a role</option
										>{#each roles as role}<option value={role.id}>{role.name}</option
											>{/each}</select
									></label
								>{/if}
							<button class="primary" type="submit">Save user</button>
						</fieldset>
					</form>
				</section>{/if}
		</div>
	{/if}
</div>

<style>
	.credential {
		display: block;
		user-select: all;
		padding: 0.75rem 0;
		font-size: 1.25rem;
	}
	.access-page {
		max-width: 80rem;
		margin: auto;
		color: var(--color-on-surface);
	}
	h1 {
		font-size: 1.5rem;
		font-weight: 700;
	}
	h2 {
		font-size: 1.15rem;
		font-weight: 700;
	}
	h3 {
		margin-top: 1rem;
		font-weight: 600;
	}
	header p,
	fieldset p,
	small {
		color: var(--color-on-surface-variant);
		font-size: 0.85rem;
	}
	.columns {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 1.5rem;
		margin-top: 1.5rem;
	}
	section {
		border: 1px solid var(--color-outline-variant);
		background: var(--color-surface);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}
	.heading,
	.list-row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}
	.list-row {
		border-bottom: 1px solid var(--color-outline-variant);
		padding-bottom: 0.75rem;
	}
	.name {
		text-align: left;
		border: 0;
	}
	small {
		display: block;
	}
	fieldset {
		border: 0;
		padding: 0;
		margin-top: 1.5rem;
	}
	legend {
		font-weight: 700;
		margin-bottom: 1rem;
	}
	label {
		display: grid;
		gap: 0.4rem;
		margin-bottom: 0.8rem;
		font-size: 0.9rem;
	}
	.choice {
		display: flex;
		align-items: center;
	}
	input:not([type='checkbox']),
	select {
		border: 1px solid var(--color-outline-variant);
		border-radius: 0.4rem;
		padding: 0.65rem;
		background: var(--color-surface-container-low);
		width: 100%;
	}
	button {
		border: 1px solid var(--color-outline-variant);
		border-radius: 0.4rem;
		padding: 0.5rem 0.75rem;
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.5;
		cursor: wait;
	}
	.primary {
		background: var(--color-primary);
		color: var(--color-on-primary);
		margin-top: 1rem;
	}
	table {
		width: 100%;
		margin: 1rem 0;
	}
	th,
	td {
		padding: 0.5rem;
		text-align: left;
	}
	.message {
		padding: 0.75rem;
		background: var(--color-surface-container);
		border-radius: 0.5rem;
		margin-top: 1rem;
	}
	.error {
		color: var(--color-error);
	}
	@media (max-width: 800px) {
		.columns {
			grid-template-columns: 1fr;
		}
	}
</style>
