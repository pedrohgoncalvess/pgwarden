import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, unmount, tick } from 'svelte';
import AccessSettings from './AccessSettings.svelte';
import PasswordPage from '../../../routes/(app)/settings/password/+page.svelte';

const mocks = vi.hoisted(() => ({ accessApi: vi.fn(), fetch: vi.fn(), projects: vi.fn() }));
vi.mock('$lib/access', () => ({ accessApi: mocks.accessApi }));
vi.mock('$lib/api', () => ({ listDatabases: async () => [], listServers: async () => [] }));
vi.mock('$lib/projects-api', () => ({ listProjects: mocks.projects }));
vi.mock('$lib/auth', () => ({ apiFetch: mocks.fetch, authHeaders: () => ({}) }));

describe('identity settings', () => {
    let component: ReturnType<typeof mount>;
    let target: HTMLDivElement;
    beforeEach(() => {
        vi.clearAllMocks();
        target = document.createElement('div');
        document.body.append(target);
        mocks.projects.mockResolvedValue([]);
        mocks.accessApi.mockImplementation(async (_path: string, method?: string) =>
            method === 'POST' ? {id: 1, email: 'new@example.com', generated_password: 'Ab1!cd2@'} : []
        );
    });
    afterEach(async () => {
        if (component) await unmount(component);
        target.remove();
    });
    async function fill(input: HTMLInputElement, value: string) {
        input.value = value;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        await tick();
    }
    it('keeps roles and users in separate screens', async () => {
        component = mount(AccessSettings, {target, props: {mode: 'roles'}});
        await vi.waitFor(() => expect(target.querySelector('legend')?.textContent).toBe('Create role'));
        expect(target.textContent).not.toContain('Create user');
        expect(mocks.accessApi).not.toHaveBeenCalledWith('users');
    });
    it('creates users without a manual password and shows the generated credential once', async () => {
        component = mount(AccessSettings, {target, props: {mode: 'users'}});
        await vi.waitFor(() => expect(target.querySelector('legend')?.textContent).toBe('Create user'));
        expect(target.textContent).not.toContain('Create role');
        expect(target.querySelector('input[type=password]')).toBeNull();
        expect(mocks.projects).not.toHaveBeenCalled();
        const inputs = target.querySelectorAll<HTMLInputElement>('input');
        await fill(inputs[0], 'New user');
        await fill(inputs[1], 'new@example.com');
        target.querySelector<HTMLInputElement>('input[type=checkbox]')!.click();
        await tick();
        target.querySelector('form')!.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
        await vi.waitFor(() => expect(target.textContent).toContain('Ab1!cd2@'));
        expect(mocks.accessApi).toHaveBeenCalledWith('users', 'POST', {
            name: 'New user', email: 'new@example.com', is_admin: true, role_id: null
        });
        [...target.querySelectorAll('button')].find(button => button.textContent === 'Dismiss')!.click();
        await tick();
        expect(target.textContent).not.toContain('Ab1!cd2@');
    });
    it('checks confirmation and submits all three password fields', async () => {
        component = mount(PasswordPage, {target});
        await tick();
        await fill(target.querySelector<HTMLInputElement>('[name=current_password]')!, 'Old!1234');
        await fill(target.querySelector<HTMLInputElement>('[name=new_password]')!, 'New!1234');
        await fill(target.querySelector<HTMLInputElement>('[name=confirm_password]')!, 'Other!12');
        const form = target.querySelector('form')!;
        form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
        await tick();
        expect(target.querySelector('[role=alert]')?.textContent).toContain('must match');
        expect(mocks.fetch).not.toHaveBeenCalled();
        await fill(target.querySelector<HTMLInputElement>('[name=confirm_password]')!, 'New!1234');
        mocks.fetch.mockResolvedValue(new Response(null, {status: 204}));
        form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
        await vi.waitFor(() => expect(target.querySelector('[role=status]')?.textContent).toContain('has been changed'));
        expect(JSON.parse(mocks.fetch.mock.calls[0][1].body)).toEqual({
            current_password: 'Old!1234', new_password: 'New!1234', confirm_password: 'New!1234'
        });
        expect(target.querySelector<HTMLInputElement>('[name=current_password]')!.value).toBe('');
    });
});
