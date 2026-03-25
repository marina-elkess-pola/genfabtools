// Simple dev-aware fetch helper
// - Prefixes API requests with '/api' during dev proxy
// - Attaches a dev token when NODE_ENV=development for backend bypass

// =============================================================================
// DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
// v2 engine feature flag: if URL contains ?v2=1, enable v2 mode
// =============================================================================
export function isV2Enabled() {
    if (typeof window === 'undefined') return false;
    const params = new URLSearchParams(window.location.search);
    return params.get('v2') === '1';
}

export function getV2Flags() {
    if (!isV2Enabled()) return {};
    // DEV ONLY — REMOVE BEFORE PUBLIC RELEASE
    const flags = {
        useV2: true,
        allowAngledParking: true,
        angle: 45,
        recoverResidual: true,
    };
    if (import.meta.env.DEV) {
        console.log('[V2 FLAGS] getV2Flags() returning:', flags);
    }
    return flags;
}
// =============================================================================

export async function apiFetch(path, options = {}) {
    const isDev = import.meta.env.DEV;
    const envBase = import.meta.env.VITE_API_URL || '';
    const base = envBase || '/api';
    const url = path.startsWith('/') ? `${base}${path}` : `${base}/${path}`;
    const headers = new Headers(options.headers || {});
    if (isDev && !headers.has('Authorization')) {
        headers.set('Authorization', 'Bearer dev-fake-token');
    }
    try {
        const resp = await fetch(url, { ...options, headers, credentials: 'include' });
        if (!resp.ok) {
            const text = await resp.text().catch(() => '');
            throw new Error(`API ${resp.status} ${resp.statusText}: ${text}`);
        }
        const ct = resp.headers.get('content-type') || '';
        if (ct.includes('application/json')) return resp.json();
        return resp.text();
    } catch (err) {
        // Suppress noisy connection errors in dev when backend isn't running
        if (isDev) {
            try { console.info('[api2] dev API suppressed', { url, message: err?.message }); } catch (e) { }
            return null;
        }
        throw err;
    }
}

export async function getMe() {
    return apiFetch('/me');
}
