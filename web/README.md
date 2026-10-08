# Researcher HMI

React and Vite frontend for the DIAL Control Center. It shows the two test
rooms, sets panel and group tint levels, runs routines, and graphs live and
historical sensor data from the control service in `svc/`.

## Entry point

`index.html` loads `src/main-hmi.tsx`, which wraps the app in `ToastProvider`
and `BrowserRouter` and renders `src/AppHMI.tsx` on `/`.

`src/main.tsx`, `src/App.tsx`, and `src/styles.css` are a legacy entry.
`index.html` does not load them, but `src/App.test.tsx` still imports `App.tsx`,
so leave them in place until that test is retired.

Routes (`src/main-hmi.tsx`):

| Path | Component |
|---|---|
| `/` | `AppHMI`: control and sensor dashboard |
| `/docs` | `components/Docs`: general operator guide |
| `/docs/routines` | `components/RoutineDocs`: routine scripting reference |
| `/docs/sensors` | `components/SensorDocs`: sensor connection and setup |

The backend's Swagger UI lives at `/api/docs`, so it does not collide with
these routes when the backend serves the built HMI.

## API base

`src/api.ts` prefixes every request with `VITE_API_BASE` (trailing slash
removed). `.env.development` sets it to `http://127.0.0.1:8000`, and Vite loads
that file only for `npm run dev`. A production build has no value, so requests
go to the same origin. The backend serves `web/dist` on port 8000 (see
`WEB_DIST_DIR` in `svc/README.md`); run `npm run build` first when you want the
backend to serve the HMI.

## Mock fallback

`AppHMI.tsx` refreshes every 5 seconds by requesting `/panels`, `/groups`,
`/health`, `/sensors`, and `/metrics/latest`. If any of those fails, it switches
to in-browser mock data from `src/mockData.ts` until a later refresh succeeds.
The header shows a `MOCK MODE` badge and the health text ends in `(mock)`.
Panel and group commands then change only the mock state, and sensor metrics
and logs are unavailable. If you see the badge on the trailer, the HMI cannot
reach the API and your commands are not reaching Halio.

## Scripts

```powershell
npm ci                    # install
npm run dev               # Vite dev server on http://localhost:5173
npm run build             # production build to dist/
npm run preview           # serve dist/ locally
npm test                  # vitest run
npm run test:watch        # vitest in watch mode
npm run typecheck         # tsc --noEmit
npm run typecheck:watch   # tsc --noEmit --watch
npm run watch             # repository error watcher, see the root README
```

`watch`, `watch:frontend`, `watch:backend`, and `watch:both` call
`../scripts/watch.mjs`. Run from `web`, `npm run watch` defaults to the frontend
type check only.

Node.js 20 or newer is required.
