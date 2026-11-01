/** Small browser-only cache for the shared server/database catalog. Never cache credentials or metrics. */
export function createCatalogCache(ttl = 15_000) {
	let owner: string | null = null;
	let generation = 0;
	const entries = new Map<string, { expires: number; response: Response }>();
	const pending = new Map<string, Promise<Response>>();
	function clear() {
		generation++;
		entries.clear();
		pending.clear();
	}
	async function read(
		key: string,
		token: string | null,
		load: () => Promise<Response>
	): Promise<Response> {
		if (owner !== token) {
			clear();
			owner = token;
		}
		const cached = entries.get(key);
		if (cached && cached.expires > Date.now()) return cached.response.clone();
		let request = pending.get(key);
		if (!request) {
			const version = generation;
			request = load()
				.then((response) => {
					if (response.ok && version === generation)
						entries.set(key, { response: response.clone(), expires: Date.now() + ttl });
					return response;
				})
				.finally(() => {
					if (version === generation) pending.delete(key);
				});
			pending.set(key, request);
		}
		return (await request).clone();
	}
	return { read, clear };
}
