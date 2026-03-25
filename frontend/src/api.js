// Simple dev-aware fetch helper
// - Prefixes API requests with '/api' during dev proxy
// - Attaches a dev token when NODE_ENV=development for backend bypass

export async function apiFetch(path, options = {}) {
    const isDev = import.meta.env.DEV;
    const base = '/api';
    const url = path.startsWith('/') ? `${base}${path}` : `${base}/${path}`;
    const headers = new Headers(options.headers || {});
    if (isDev && !headers.has('Authorization')) {
        headers.set('Authorization', 'Bearer dev-fake-token');
    }
    const resp = await fetch(url, { ...options, headers, credentials: 'include' });
    if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`API ${resp.status} ${resp.statusText}: ${text}`);
    }
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) return resp.json();
    return resp.text();
}

export async function getMe() {
    return apiFetch('/me');
}
