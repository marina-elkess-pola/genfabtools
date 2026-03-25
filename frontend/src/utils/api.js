const BASE = import.meta.env.VITE_API_URL || '';

async function request(method, path, body) {
    const token = localStorage.getItem('token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;

    const opts = { method, headers, credentials: 'include' };
    if (body !== undefined) opts.body = JSON.stringify(body);

    const res = await fetch(BASE + path, opts);

    if (res.status === 401) {
        localStorage.removeItem('token');
        window.dispatchEvent(new Event('auth-change'));
        try {
            localStorage.setItem('postAuthRedirect', window.location.pathname + window.location.search);
        } catch (_) { /* storage full / denied */ }
        window.location.href = '/login';
        return;
    }

    return res;
}

const api = {
    get: (path) => request('GET', path),
    post: (path, body) => request('POST', path, body),
    put: (path, body) => request('PUT', path, body),
    delete: (path, body) => request('DELETE', path, body),
};

export default api;
