import { error } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

async function forward(request: Request, url: URL) {
	const backendUrl = env.API_URL || 'http://localhost:8080';
	const targetUrl = `${backendUrl}${url.pathname.replace(/^\/api/, '')}${url.search}`;

	const requestHeaders = new Headers(request.headers);
	requestHeaders.delete('host'); 

	try {
		const response = await fetch(targetUrl, {
			method: request.method,
			headers: requestHeaders,
			body:
				request.method !== 'GET' && request.method !== 'HEAD'
					? await request.arrayBuffer()
					: undefined,
			// @ts-ignore
			duplex: 'half'
		});

		return new Response(response.body, {
			status: response.status,
			headers: response.headers
		});
	} catch (err) {
		throw error(500, 'Error connecting to backend API');
	}
}

export const GET: RequestHandler = ({ request, url }) => forward(request, url);
export const POST: RequestHandler = ({ request, url }) => forward(request, url);
export const PUT: RequestHandler = ({ request, url }) => forward(request, url);
export const DELETE: RequestHandler = ({ request, url }) => forward(request, url);
export const PATCH: RequestHandler = ({ request, url }) => forward(request, url);
