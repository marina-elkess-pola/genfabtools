# Tools Page — QA Checklist & Preview

This document collects commands, checks, and acceptance criteria to QA the Tools page locally.

---

## Goals

- Verify the new glass header (backdrop blur + engraved text) renders correctly.
- Confirm Tools page palette (whites/greys/blacks) is applied across header, sidebar, tool cards, and details panel.
- Ensure the homepage dropdown and menu behaviors remain correct (no black rectangle on click).
- Validate responsiveness, accessibility, and basic performance.

---

## Quick start — dev server (Windows cmd.exe)

Open a terminal and run:

```cmd
cd /d c:\Users\Personal\OneDrive\Desktop\Marina\pytho\website\occupant_calculator\frontend
npm install    # only if you haven't installed dependencies yet
npm run dev
```

- Note: Vite may pick a fallback port if 5173 is in use. Use the URL shown in the console.
- If changes don't appear, stop the server (Ctrl+C) and restart it; OneDrive file-watching can be flaky.

---

## Build & preview (production-like)

```cmd
cd /d c:\Users\Personal\OneDrive\Desktop\Marina\pytho\website\occupant_calculator\frontend
npm run build
npx serve -s build  # or npm i -g serve && serve -s build
```

Visit the served URL to verify the production build.

---

## Browser checks (manual)

1. Open the Tools page (`/tools`).
2. Visual checks
   - Glass header is visible with backdrop blur and slightly stronger tint.
   - Header text reads as "engraved" (subtle highlight + inset shadow).
   - CTA appears as a subtle ghost on the glass panel and is keyboard-focusable.
   - Sidebar filters panel is light grey and the search input is accessible.
   - Tool cards use whites/greys/blacks with a dark CTA pill and hover lift.
   - Slide-over details is white with slate text and dark CTA.
3. Interaction checks
   - Open a tool card — details slide-over opens and can be closed with mouse and keyboard.
   - Keyboard navigation: tab order works; logo-only buttons have `aria-label`.
   - Menu button on homepage toggles dropdown; clicking logo does not leave a black rectangle.
4. Responsiveness
   - Mobile widths: cards stack full-width; sidebar moves below header or collapses naturally.
   - Tablet and Desktop: grid columns adjust (1 → 2 → 3 columns depending on width).

---

## Automated checks (optional)

- Lighthouse (install via npm or use Chrome DevTools):

```cmd
# from local dev server (replace port/url as needed)
npx lighthouse http://localhost:5173/tools --output html --output-path=tools-lighthouse.html
```

- Axe accessibility CLI (or use the axe DevTools browser extension):

```cmd
npx @axe-core/cli http://localhost:5173/tools
```

Note: these may require additional npm packages or running in a headless environment.

---

## Performance & assets

- Confirm hero video loads and has `playsInline`, `muted`, `autoplay`, and a `poster` if available.
- Ensure only one copy of `genfabtools-logo-animation.mp4` is used (prefer `public/` or `src/assets` consistently).
- Card icons should use `loading="lazy"` to reduce initial load.

---

## Acceptance criteria (pass/fail)

- [ ] Header glass renders (backdrop blur + tint) and the title displays the engraved effect.
- [ ] Tools palette uses neutral whites/greys/blacks across the page.
- [ ] No black rectangle appears when interacting with menu or dropdown.
- [ ] Cards open slide-over details; all actions accessible via keyboard.
- [ ] Mobile/tablet/desktop breakpoints show appropriate layout changes (no overlap/clipped text).
- [ ] Basic Lighthouse score: Performance/Accessibility best-effort (you decide threshold).

---

## Troubleshooting

- If CSS changes don't appear:
  - Hard refresh (Ctrl+Shift+R) or disable cache in DevTools.
  - Restart the dev server.
  - If working inside OneDrive, consider temporarily moving the project outside of OneDrive if file-watching fails.
- If dev server shows `port in use`, use the fallback port from Vite's console.

---

## How to report issues

Create a short issue with: reproduction steps, OS/browser, a screenshot (if visual), and console output (if error). Prioritize: blocking runtime errors > major accessibility > visual polish.

---

## Next steps after QA

- If header or text engraving needs stronger/softer effect, tune these values in `frontend/src/index.css` (`.engraved-text` definitions).
- If performance is a concern, canonicalize assets and lazy-load icons.

---

Feel free to ask me to run any of the checks or to apply further tweaks (stronger engraving, different tint, CTA style), and I’ll make the edits.
