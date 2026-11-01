<script lang="ts">
	let email = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleLogin(e: Event) {
		e.preventDefault();
		error = '';
		loading = true;

		try {
			const res = await fetch('/api/v1/auth', {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json'
				},
				body: JSON.stringify({ email, password })
			});

			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				error = data.detail || 'Falha ao autenticar. Verifique suas credenciais.';
				return;
			}

			const data = await res.json();
			localStorage.setItem('token', data.access_token.token);
			window.location.href = '/overview';
		} catch (err) {
			error = 'Erro de conexão com o servidor.';
		} finally {
			loading = false;
		}
	}
</script>

<div
	class="flex min-h-screen items-center justify-center p-container-padding bg-background relative overflow-hidden"
>
	<main class="w-full max-w-[420px] z-10">
		<div class="flex flex-col items-center text-center space-y-4 mb-8">
			<img
				src="/branding/logo.jpg"
				alt="pgwarden logo"
				class="w-16 h-16 rounded-2xl object-cover shadow-lg shadow-primary/20"
			/>
			<div>
				<h1 class="font-headline-lg text-3xl font-bold text-on-surface tracking-tight m-0 mb-2">
					pgwarden
				</h1>
				<p class="font-body-md text-on-surface-variant max-w-[280px] text-sm">
					Secure gateway for high-performance PostgreSQL cluster management.
				</p>
			</div>
		</div>

		<section class="glass-panel p-8 shadow-floating">
			<form onsubmit={handleLogin} class="space-y-6" id="loginForm">
				<div class="flex flex-col gap-2">
					<label
						class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
						for="email">Email</label
					>
					<div class="relative group">
						<span
							class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant group-focus-within:text-primary transition-colors text-[20px]"
							>mail</span
						>
						<input
							bind:value={email}
							class="input-technical text-code-md pl-11 pr-4 py-3 w-full"
							id="email"
							name="email"
							placeholder="admin@example.com"
							required
							type="email"
						/>
					</div>
				</div>

				<div class="flex flex-col gap-2">
					<label
						class="text-xs font-bold uppercase tracking-wider text-on-surface-variant"
						for="password">Password</label
					>
					<div class="relative group">
						<span
							class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant group-focus-within:text-primary transition-colors text-[20px]"
							>lock</span
						>
						<input
							bind:value={password}
							class="input-technical text-code-md pl-11 pr-4 py-3 w-full tracking-widest"
							id="password"
							name="password"
							placeholder="••••••••"
							required
							type="password"
						/>
					</div>
				</div>

				{#if error}
					<div
						class="bg-error-container/20 border-l-4 border-error p-3 rounded mt-2 flex items-start gap-2"
					>
						<span class="material-symbols-outlined text-error text-[18px]">error</span>
						<p class="font-code-sm text-xs text-error mt-0.5">{error}</p>
					</div>
				{/if}

				<div class="pt-4">
					<button
						disabled={loading}
						class="btn-primary w-full py-3 font-headline-md text-base font-bold flex items-center justify-center gap-2 cursor-pointer disabled:opacity-70 disabled:cursor-wait"
						type="submit"
					>
						{#if loading}
							<svg
								class="animate-spin h-5 w-5 text-on-primary-container"
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
							>
								<circle
									class="opacity-25"
									cx="12"
									cy="12"
									r="10"
									stroke="currentColor"
									stroke-width="4"
								></circle>
								<path
									class="opacity-75"
									fill="currentColor"
									d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
								></path>
							</svg>
						{/if}
						<span>Connect</span>
					</button>
				</div>
			</form>
		</section>
	</main>
</div>
