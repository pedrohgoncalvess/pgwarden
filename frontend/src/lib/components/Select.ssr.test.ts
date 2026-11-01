import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import Select from './Select.svelte';

describe('Select server rendering', () => {
	it('shows the selected label without waiting for JavaScript or an icon font', () => {
		const { body } = render(Select, {
			props: {
				options: [{ value: 'require', label: 'Require SSL' }],
				value: 'require',
				'aria-label': 'SSL mode'
			}
		});
		expect(body).toContain('Require SSL');
		expect(body).toContain('role="combobox"');
		expect(body).not.toContain('<select');
	});
	it('provides a placeholder when options have not loaded', () => {
		const { body } = render(Select, {
			props: { options: [], placeholder: 'Select a server', 'aria-label': 'Server' }
		});
		expect(body).toContain('Select a server');
		expect(body).toContain('aria-expanded="false"');
	});
});
