# Development dev server

The Vite dev server can be started with:

  cd frontend
  npm run dev

By default Vite tries port 5173. If that port is in use, it will auto-increment (5174, 5175...). To start explicitly on a chosen port (e.g., 5175):

  npx vite --host 127.0.0.1 --port 5175

If you want to force 5173, stop any other node/vite processes on your machine and run:

  npx vite --host 127.0.0.1 --port 5173

## Troubleshooting

- If the favicon doesn't update, hard-refresh the page (Ctrl+F5) or clear browser cache.

- To find processes listening on port 5173 (Windows):

    netstat -aon | findstr :5173

  Then kill the PID returned with:

    taskkill /PID PID /F

## Generating icons (recommended)

To ensure cross-browser compatibility, generate PNG icons and a favicon.ico from the SVG and place them in `frontend/public/`.

If you have ImageMagick installed locally, run these commands from the project root:

```cmd
cd C:\Users\Personal\OneDrive\Desktop\Marina\pytho\website\occupant_calculator\frontend\public
# create 192x192 and 512x512 PNGs from the SVG
magick convert occucalc-logo.svg -resize 192x192 icon-192.png
magick convert occucalc-logo.svg -resize 512x512 icon-512.png
# create favicon.ico (contains multiple sizes)
magick convert icon-192.png icon-512.png favicon.ico
```

After that, restart the dev server and hard-refresh your browser.
