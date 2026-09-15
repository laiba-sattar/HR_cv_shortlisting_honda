# HR CV Shortlisting System — Frontend

Frontend for the Honda Atlas Cars Pakistan HR CV Shortlisting System internship
project. Covers the full flow from the Part 3 frontend specification — but
consolidated onto a **single working page** rather than a multi-step wizard, built
with **React + TypeScript + Vite + Tailwind CSS**, in a red/white color
scheme inspired by Honda's brand colors.

> **This is a frontend-only build.** There is no backend yet (that's the next
> phase). To make every screen demonstrable end-to-end right now, the JD
> parsing, CV processing, and candidate scoring are simulated client-side —
> see **"How the demo data works"** below. Swapping the simulation for real
> API calls only touches a handful of files (also listed below).

## Quick start

Requires [Node.js](https://nodejs.org) `20.19+` or `22.12+` (see **Environment
& isolation** below for why, and how to pin it exactly).

```bash
npm install
npm run dev
```

Then open the URL it prints (usually `http://localhost:5173`). Sign in with
either demo role on the login screen — no real credentials needed yet.
Stop the server with `Ctrl+C` in the terminal when you're done.

## Environment & isolation

Every Node.js project is automatically isolated — `npm install` downloads
this project's dependencies into a local `node_modules/` folder **inside
this project's own directory only**. It does not touch, upgrade, or share
anything with other Node projects on your machine, and nothing here needs a
separate virtual environment the way Python does. You can delete
`node_modules/` at any time and `npm install` will recreate it from
`package.json` and `package-lock.json` (the lock file pins the exact
dependency versions, so a fresh install always reproduces the same result).

The one thing that *is* shared across projects is the Node.js runtime
itself. This project is pinned to Node `20.19+` or `22.12+` two ways:

- `package.json` → `"engines"` — `npm install` will warn if your global
  Node version doesn't satisfy this.
- `.nvmrc` — if you use [nvm](https://github.com/nvm-sh/nvm) to manage
  multiple Node versions, run `nvm use` inside this folder and it will
  switch to the exact version this project was built and tested against,
  without affecting any other project's Node version.

Check what you currently have with `node -v`. If it's older than `20.19`,
either install a newer Node from [nodejs.org](https://nodejs.org) (the LTS
build), or use `nvm install && nvm use` if you have nvm.

To build a static production bundle:

```bash
npm run build      # outputs to dist/
npm run preview    # serves the built dist/ folder locally, to sanity-check it
```

`dist/` cannot be opened by double-clicking `index.html` — browsers block
ES-module scripts loaded via `file://`. Serve it instead, e.g. `npx serve dist`,
or deploy it to any static host / internal web server.

## Layout — one working page

The whole ranking flow lives on a **single page** (`/`), split into two panels:

- **Set up** (left) — saved roles, job title, job description (upload or
  paste), the JD requirement check, required skills, and CV upload.
- **Shortlist** (right) — empty state, validation errors, live processing
  progress, then the ranked results.

There is exactly **one action button: “Rank CVs.”** Pressing it:

1. Runs the JD requirement check first (age / experience / qualification).
2. If anything is missing — a field not found in the advert and not typed in
   by hand, no skills, no CVs, no title — it stops and lists every problem in
   the Shortlist panel, and highlights the missing fields in amber on the
   left. Nothing is processed.
3. If everything checks out, it processes the CVs and renders the ranked
   shortlist in the same panel. Click any candidate row to expand the full
   score breakdown in place.

| Route | Page |
|-------|------|
| `/` | **Workspace** — the entire flow above |
| `/history` | Saved Roles & History (open one to load it back into the workspace) |
| `/admin` | Admin Panel (Admin role only) |
| `/help` | Help / FAQ |
| `/login` | Login |

Switch between **HR User** and **Admin** roles with the toggle in the header
to see role-gated views (Admin Panel is hidden/blocked for HR User).

### The JD requirement check

Age, experience and qualification are detected with keyword/pattern matching
over the advert text, and the matched sentence is shown back to you as
evidence. Anything not found becomes a required manual field. A value you
type in **always overrides** what was detected in the advert — that rule is
stated in the UI next to each Edit control.

Pasting the advert gives a real check; uploading a PDF/DOCX falls back to a
simulated result, because reading those formats needs the backend parser
(a `.txt` upload is read for real).

## How the demo data works

There's no backend to call yet, so `src/context/AppContext.tsx` holds all
"saved roles" in memory (persisted to `localStorage` so it survives a page
refresh) and seeds three example jobs on first load (`src/data/seed.ts`).

- **JD requirement check** (`src/utils/simulate.ts` → `analyzeJD`) — for
  pasted text this is genuinely rule-based: regex/keyword patterns look for
  age, experience and qualification statements and return the matched
  sentence as evidence. Only file uploads (PDF/DOCX, which the browser can't
  read without the backend parser) fall back to a simulated result.
- **Candidate generation & scoring** (`src/data/generate.ts`) — generates
  plausible mock candidates (names, degrees, work history, skills) with
  randomized-but-weighted scores whenever you press Rank CVs. This stands in
  for the extraction pipeline and scoring engine described in Part 1 and
  Part 2 of the project spec.
- **File processing** (the `runProcessing` function in
  `src/pages/Workspace.tsx`) simulates the async, per-file progress described
  in the architecture doc, including occasional simulated failures
  (unreadable scan / corrupted file) that are reported and excluded from the
  ranking — so the failure-handling UI is real even though the failures are
  fake.

None of this is real candidate data — names, emails, and scores are
generated from placeholder word lists in `src/data/pools.ts`.

## Wiring up the real backend later

When the backend from Parts 1–2 of the project exists, replace the
simulated pieces with real API calls in these spots — the UI components
themselves don't need to change:

- `src/utils/simulate.ts` → replace `analyzeJD` with a call to the JD Intake
  Service endpoint. The `readRequirements()` function in `Workspace.tsx` is
  the only caller, and it already returns `{ profile, skills }`, so making it
  async is a contained change.
- `runProcessing` in `src/pages/Workspace.tsx` → replace the local
  file-status simulation with an upload + polling (or websocket) against the
  Job Orchestration & Async Queue endpoint. The `phase` state
  (`idle`/`processing`/`done`) already models exactly the states the real
  endpoint reports.
- `src/data/generate.ts` → remove entirely once the Scoring & Ranking
  Engine returns real candidate profiles and scores over the API.
- `src/context/AppContext.tsx` → swap the `localStorage`-backed job list for
  fetches against the real `/jobs` API, keeping the same `JobRun` shape
  (`src/types.ts`) so the pages don't need rewriting.

The validation logic in `handleRank()` should stay on the client as a fast
first check, but must be repeated server-side — the "JD upload required" and
"manual value overrides JD" rules are business rules, and a frontend check
alone can be bypassed by calling the API directly.

## Project structure

```
src/
  components/     AppHeader (header + nav), Layout (shell for secondary
                  pages), Logo, and shared UI primitives in ui.tsx
  context/        AppContext — localStorage-backed job store, current role
  data/           Mock candidate generators and seed roles (demo only)
  pages/
    Workspace.tsx   THE main page — set-up panel + shortlist panel
    SavedRoles.tsx  History
    Admin.tsx       Admin panel
    Help.tsx        FAQ
    Login.tsx       Sign-in
  utils/simulate.ts  JD analysis + file-outcome stand-ins
  types.ts        Shared types (JobRun, Candidate, JDProfile, ...)
```

## Branding note

The colors (`#E2231A` red / white / dark charcoal) are inspired by Honda's
brand palette, defined in `tailwind.config.js` under the `honda` and `ink`
color keys. The logo in `src/components/Logo.tsx` is a plain text/geometric
wordmark, **not** a reproduction of Honda's trademarked "H" emblem — swap it
for an official approved logo asset once IT/Legal provides one.

## Notes

- Routing uses `HashRouter` (URLs look like `/#/roles`) so the built site
  works when opened from any sub-path or static host without server-side
  rewrite rules — switch to `BrowserRouter` once it's deployed behind a
  real web server that can be configured for SPA fallback routing.
- Decision-support framing is intentional throughout the UI (banner text,
  the optional-only status tags on Candidate Detail, etc.) — this mirrors
  the "ranks and explains, human decides" principle from the architecture
  document and shouldn't be removed when the backend is wired up.
