# Frontend Architecture

## Stack

- package manager: `pnpm`
- framework: `Nuxt 4`
- UI runtime: `Vue 3`
- language: `TypeScript`

## Current Structure

Current UI is split into a light app shell plus page routes:

- app shell: `frontend/app/app.vue`
- chat homepage: `frontend/app/pages/index.vue`
- document workspace: `frontend/app/pages/documents.vue`
- sidebar navigation: `frontend/app/components/AppSidebar.vue`
- runtime config: `frontend/nuxt.config.ts`

## Current Responsibilities

- chat-first landing page and prompt composer UI
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

- chat homepage with a soft neutral background and app-like sidebar
- rounded input/composer surface for future AI interaction
- separate document workspace for upload and list management
- warm neutral surfaces instead of a dense dashboard-only layout

This gives room for later expansion into:

- document detail pages
- fragment preview pages
- vectorization history
- retrieval and real chat interfaces
