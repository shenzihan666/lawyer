<script setup lang="ts">
import { useUiStore } from "../stores/ui";

const uiStore = useUiStore();
</script>

<template>
  <UApp>
    <div
      class="min-h-screen bg-[#fcfbf8] font-sans text-zinc-900 selection:bg-zinc-200"
    >
      <NuxtRouteAnnouncer />

      <div
        class="sticky top-0 z-30 border-b border-[#ebe5da] bg-[#fcfbf8]/90 backdrop-blur md:hidden"
      >
        <div class="flex items-center justify-between px-4 py-3">
          <div class="flex items-center gap-3">
            <div
              class="flex h-9 w-9 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-black/5"
            >
              <span class="text-sm font-semibold text-zinc-900">豆</span>
            </div>
            <div>
              <p class="text-sm font-semibold text-zinc-900">豆包</p>
              <p class="text-xs text-zinc-500">AI 助手界面</p>
            </div>
          </div>
          <UButton
            icon="i-lucide-menu"
            color="neutral"
            variant="ghost"
            @click="uiStore.openMobile()"
          />
        </div>
      </div>

      <AppSidebar />

      <main class="min-h-screen md:pl-[264px]">
        <NuxtPage />
      </main>
    </div>
  </UApp>
</template>
