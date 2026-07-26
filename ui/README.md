# FDE Console

React frontend for the Brain. Runs entirely on fixtures right now; flips to the live
Brain by changing one file.

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # -> dist/, static, serve from anywhere
```

## Layout

```
src/
  api/
    types.ts       # mirror of CONTRACT.md — the seam
    fixtures.ts    # dummy data (stale DB_HOST scenario)
    mock.ts        # ConsoleApi backed by fixtures, streams token by token
    live.ts        # ConsoleApi backed by the Brain over fetch + SSE
    client.ts      # picks one; nothing else imports mock or live
  store/useStore.ts
  panels/          # Agent, Graph, Logs, Process
  components/      # Header, MachineRail
  lib/             # formatting, dagre layout
```

## Wiring the Brain

Nothing outside `src/api/` knows whether data is real. To go live:

1. Make the Brain serve four routes matching `ConsoleApi` in `types.ts`:
   - `GET /api/snapshot` → `ConsoleSnapshot`
   - `POST /api/chat` → newline-delimited `TraceEvent` JSON, streamed
   - `PUT /api/context` → `{ markdown }`
   - `GET /api/stream` → SSE, each message a full `ConsoleSnapshot`
2. Click **fixtures** in the header to toggle to **brain**, or start with
   `VITE_USE_MOCK=false npm run dev`.

`vite.config.ts` proxies `/api` to `127.0.0.1:8000`, so there is no CORS to debug.
Point `VITE_BRAIN_URL` elsewhere if the Brain is on another host.

The mock streams the agent reply word by word on purpose. Both sides of the seam are
async generators, so swapping in the real stream doesn't touch the transcript UI.

## Demo-day notes

- No webfonts, no CDN anything. Renders identically with the cable unplugged.
- `npm run build` then serve `dist/` from the Brain's Python process — one origin,
  one port, nothing to explain on stage.
- Install deps **before** you lose network.

## Design

Monospace throughout, deep slate ground. Amber means live, cyan means retrieved
evidence, coral is reserved for critical so it stays meaningful. The machine rail on
the left never goes away — whatever tab you're on, you can see which box is doing what.
