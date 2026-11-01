import { redirect } from '@sveltejs/kit';
import { resolve, base } from '$app/paths';
import { canonicalPath } from '$lib/routePaths';

export function redirectLegacy(url: URL): never {
	const path = canonicalPath(url.pathname.slice(base.length));
	redirect(308, resolve(...([path] as Parameters<typeof resolve>)) + url.search);
}
