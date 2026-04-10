# PGWarden Frontend

Frontend app for PGWarden

## Stack

- Vite + React + TypeScript
- TanStack Router
- TanStack Query
- Zustand (slices pattern)
- TanStack Table + TanStack Virtual
- uPlot
- TailwindCSS
- Comlink + Web Workers
- Zod

## Structure

```text
frontend/
  public/
  src/
    app/
    lib/
    modules/
      auth/
      dashboard/
    routes/
    main.tsx
```

## Run

```bash
npm install
npm run dev
```

Default app URL: `http://localhost:5173`

## Environment

Create `.env` from `.env.example`:

```bash
cp .env.example .env
```

Available vars:

- `VITE_API_BASE_URL` default: `http://localhost:8080/v1`

## WIP

- The performance stream in `dashboard.metrics-sse.ts` is fake SSE data used for UI/UX development.
- Chart metrics and query table values in the performance panel are simulated and do not come from backend query telemetry yet.
- Query list rows (query text/role/categories) are generated from a local sample pool and rotated over time

## Scripts

- `npm run dev` - start development server
- `npm run build` - typecheck + production build
- `npm run lint` - run ESLint