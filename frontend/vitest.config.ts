import { fileURLToPath } from 'node:url';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default {
	test: {
		projects: [
			{
				extends: './vite.config.ts',
				test: {
					name: 'server',
					include: ['src/**/*.test.ts'],
					exclude: ['src/**/*.dom.test.ts']
				}
			},
			{
				plugins: [
					svelte({ emitCss: false, dynamicCompileOptions: () => ({ generate: 'client' }) })
				],
				resolve: {
					conditions: ['browser'],
					alias: {
						$lib: fileURLToPath(new URL('./src/lib', import.meta.url)),
						'$app/stores': fileURLToPath(
							new URL('./node_modules/@sveltejs/kit/src/runtime/app/stores.js', import.meta.url)
						),
						'$app/navigation': fileURLToPath(
							new URL('./node_modules/@sveltejs/kit/src/runtime/app/navigation.js', import.meta.url)
						)
					}
				},
				test: {
					name: 'dom',
					environment: 'jsdom',
					include: ['src/**/*.dom.test.ts']
				}
			}
		]
	}
};
