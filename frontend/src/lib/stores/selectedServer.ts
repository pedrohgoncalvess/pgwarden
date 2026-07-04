import { writable } from 'svelte/store';

export const selectedServerId = writable<string | null>(null);
