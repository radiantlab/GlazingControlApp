# Researcher HMI

React and Vite frontend for the DIAL Control Center. It shows the two test
rooms, sets panel and group tint levels, runs routines, and graphs live and
historical sensor data from the control service in `svc/`.

## Entry point

`index.html` loads `src/main-hmi.tsx`, which wraps the app in `ToastProvider`
and `BrowserRouter` and renders `src/AppHMI.tsx` on `/`.

Vite builds only this entry through `index.html`. The Docker image runs the
same `npm run build` and packages `dist/`. Dashboard tests live in
`src/AppHMI.test.tsx`.

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

## Historical sensor graphs (Issue #42)

On the Sensors tab, each sensor with a known metric has its own Start and End
date/time fields. Choose a range and click **Show History** to request stored
measurements for that sensor and the selected Graph metric. Changing the metric
keeps the applied range. Editing the fields alone does not change the graph;
the **Historical range** text identifies the applied selection.

Times use the browser's local timezone, shown beside the fields, and are sent
to the existing `/metrics/history` endpoint as Unix seconds. Both endpoints
are inclusive, and the end must be after the start. Nonexistent local times
(such as the spring daylight-saving gap) are rejected. When clocks go back,
a repeated time uses its first occurrence; the applied range and tooltips show
the timezone abbreviation. The graph spaces points by elapsed time and includes
dates in historical mode.

Historical graphs do not poll or follow changes in live metric freshness.
Sensor health and the adjacent live/last-reading panel continue updating.
Applied ranges survive switching between Control and Sensors or hiding and
restoring a card within the current page session; a page reload resets to live.

Loading, empty results, and failed requests have separate messages. Click
**Show History** again to retry the same range. Requests use the browser's
normal network behavior, without a custom timeout or cancellation; results
from an old selection are ignored. **Back to Live** resumes the preceding-hour graph
and polling for reporting sensors. Offline sensors retain the existing fixed
hour ending at their last reading until reporting recovers. A sensor with no
known readings keeps the existing no-reading notice rather than guessing a
metric or drawing a zero measurement.

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

Node.js 24 is required (`.nvmrc` at the repository root).
