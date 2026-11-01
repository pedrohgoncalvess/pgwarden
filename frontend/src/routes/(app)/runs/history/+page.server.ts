import type { PageServerLoad } from './$types';
import { redirectLegacy } from '$lib/server/legacyRedirect';

export const load: PageServerLoad = ({ url }) => redirectLegacy(url);
