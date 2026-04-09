# PGWarden Frontend

PGWarden query monitoring dashboard

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