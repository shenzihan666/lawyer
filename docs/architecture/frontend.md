# Frontend Architecture

## Stack

- package manager: `pnpm`
- framework: `Nuxt 4`
- UI runtime: `Vue 3`
- language: `TypeScript`

## Current Structure

Current UI is split into a light app shell plus page routes:

- app shell: `frontend/app/app.vue`
- redirect entrypoint: `frontend/app/pages/index.vue`
- grounded chat workspace: `frontend/app/pages/chat.vue`
- opponent prediction workbench: `frontend/app/pages/opponent-analysis.vue`
- document workspace: `frontend/app/pages/documents.vue`
- sidebar navigation: `frontend/app/components/AppSidebar.vue`
- chat state store: `frontend/stores/chat.ts`
- opponent analysis store: `frontend/stores/opponentAnalysis.ts`
- document state store: `frontend/stores/documents.ts`
- UI shell state store: `frontend/stores/ui.ts`
- runtime config: `frontend/nuxt.config.ts`

## Current Responsibilities

- grounded single-turn legal Q&A with citation cards
- multi-tab opponent prediction board with live process stream and replay
- left navigation with desktop and mobile variants
- drag-and-drop or picker-based file selection
- single and batch upload
- document list rendering
- batch selection
- single and batch delete
- single and batch vectorization queue actions
- surface loader, status, page count, fragment count, and hash preview

## API Integration

The frontend reads its base API URL from Nuxt runtime config:

- `public.apiBase`

Default local value:

- `http://127.0.0.1:8000/api/v1`

## UI Direction

The current frontend mixes two visual surfaces:

- chat workspace with a soft neutral background and app-like sidebar
- rounded prompt surface plus answer-and-citation panels
- separate document workspace for upload and list management
- warm neutral surfaces instead of a dense dashboard-only layout

This gives room for later expansion into:

- document detail pages
- fragment preview pages
- vectorization history
- multi-turn chat and session history
