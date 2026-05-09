# PaperLens Next.js Frontend

This directory contains the new Next.js frontend for PaperLens. It replicates the current Streamlit prototype while upgrading the UI into a more polished research workstation with streaming chat, interactive mind maps, and a stronger flashcard study experience.

## Stack

- Next.js App Router with TypeScript
- Tailwind CSS and hand-authored shadcn-style UI primitives
- `@tanstack/react-query` for client-side data fetching
- `@xyflow/react` for the mind map canvas
- `framer-motion` for page and study-card motion
- `zod` for runtime schema validation
- Vitest for utility and interaction tests

## Routes

- `/`
  - Landing page equivalent of the Streamlit `app.py` overview.
- `/papers`
  - Search and filter papers, manage bookmarks, preview PDFs, open mind maps, and study flashcards.
- `/chat`
  - Streaming RAG assistant with the same controls as the Streamlit chat page.
- `/api/*`
  - Same-origin proxy routes that forward requests to the FastAPI backend.

## Why the proxy layer exists

The browser does not call FastAPI directly. The current backend does not expose CORS configuration for a standalone browser frontend, so the Next app proxies the needed endpoints through route handlers under `app/api`. That keeps the browser same-origin while still using the existing backend contracts.

## Environment

The frontend uses one server-side environment variable:

```bash
PAPERLENS_API_BASE_URL=http://localhost:8000/api/v1
```

Use `http://localhost:8000/api/v1` for host-based local development.
Use `http://api:8000/api/v1` inside Docker Compose.

## Project structure

```text
new-frontend/
├── app/
│   ├── api/                 # Next proxy handlers for papers, chat, and visualizations
│   ├── chat/                # Streaming assistant route
│   ├── papers/              # Research shelf route
│   ├── globals.css          # Design tokens, base styles, and React Flow styles
│   └── page.tsx             # Overview landing page
├── components/
│   ├── chat/                # Streaming chat interface
│   ├── navigation/          # Header and top-level nav
│   ├── papers/              # Paper cards, dialogs, mind map, flashcards
│   └── ui/                  # Shared primitives
├── lib/
│   ├── api/                 # Browser and server fetch helpers
│   ├── bookmarks.ts         # Local storage helpers
│   ├── constants.ts         # Categories, nav items, models
│   ├── env.ts               # Server-side API base URL helper
│   ├── mindmap.ts           # Tree expansion and React Flow transforms
│   ├── schemas.ts           # Zod schemas and TS types
│   ├── stream.ts            # Streaming chat parser
│   └── utils.ts             # Generic utility helpers
├── tests/                   # Vitest coverage for helpers and data parsing
├── Dockerfile               # Production-oriented container build
└── package.json             # Scripts and dependency declarations
```

## Core data flow

1. UI components call helpers from `lib/api/client.ts`.
2. Those hit same-origin Next handlers in `app/api`.
3. Route handlers call FastAPI via `lib/api/backend.ts`.
4. Responses are validated with `zod` before the UI consumes them.

This split keeps browser code simple and prevents API hostname leakage into client bundles.

## Key behavior decisions

- Paper search loads the latest papers immediately instead of waiting for the first manual search.
- Bookmarks are stored in `localStorage`, so they survive refreshes.
- PDF preview stays iframe-based to avoid cross-origin PDF viewer issues.
- Chat streams through `/api/chat/stream` by default and falls back to `/api/chat` if needed.
- Mind maps open in a dark, zoomable canvas with expand/collapse controls.
- Flashcards use a local deck state for shuffle, restart, topic filtering, and studied tracking.

## Commands

```bash
npm install
npm run dev
```

If you prefer `pnpm`, the project is configured for it and the Dockerfile uses it through Corepack:

```bash
corepack enable
pnpm install
pnpm dev
```

Useful commands:

```bash
npm run typecheck
npm run test
npm run build
```

## Docker and Compose

Build the standalone frontend container from this directory:

```bash
docker build -t paperlens-next-frontend .
```

In the repo root, `compose.yml` now exposes:

- Streamlit frontend on `http://localhost:8501`
- Next.js frontend on `http://localhost:3000`

Both depend on the same FastAPI backend.

## Adding new features safely

- If a feature needs backend data, add the proxy route first.
- Add a `zod` schema for any new response shape before consuming it in components.
- Keep browser code talking only to `lib/api/client.ts`, not directly to external URLs.
- Put reusable interface pieces in `components/ui` or a focused domain folder rather than growing page files.
- Preserve the current visual system: dark graphite shells, amber accents, serif display typography, and restrained motion.

## Onboarding checklist

1. Read `lib/schemas.ts` to understand the backend payloads.
2. Read `lib/api/backend.ts` and `app/api/*` to see how proxying works.
3. Open `components/papers` to understand the main feature surface.
4. Run the tests before changing utility or parsing logic.
5. Use the Docker Compose setup when validating end-to-end backend integration.
