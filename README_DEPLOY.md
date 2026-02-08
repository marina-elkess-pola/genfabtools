
# Deployment guide — GenFab Tools

This repo contains a static marketing site and an API backend. The recommended setup is:

- Static site: Netlify (serves marketing homepage at `www.genfabtools.com`)
- Backend/API: Render (serves API at `api.genfabtools.com`)

Files added for deployment:

- `genfab_build_netlify.zip` — Netlify-ready static bundle. Upload via Netlify UI (drag & drop).
- `backend/render.yaml` — Render manifest to use when creating a Render Web Service (fill env values in Render dashboard).

Quick steps:

1. Upload `genfab_build_netlify.zip` to Netlify (Dashboard → Sites → Add new site → Deploy manually).
2. Add custom domain `www.genfabtools.com` in Netlify and follow DNS instructions.
3. Create a Render Web Service and connect the repo; Render will detect `backend/render.yaml`.
4. In Render dashboard, set environment variables: `MONGODB_URI`, `EMAIL_USER`, `EMAIL_PASS`, `JWT_SECRET`.
5. Add a CNAME record in your DNS: `api` → the Render service host. Wait for TLS issuance.

Netlify `_redirects` (already included in the zip) proxies `/rooms` and `/api/*` to `https://api.genfabtools.com`.

If you want, I can walk through the Netlify upload and Render create-service steps while you watch.
