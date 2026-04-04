<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useUiStore } from "../stores/ui";

const uiStore = useUiStore();
const { isSidebarCollapsed } = storeToRefs(uiStore);

const mainClass = computed(() => [
  "min-h-screen transition-[padding] duration-300",
  isSidebarCollapsed.value ? "md:pl-0" : "md:pl-[264px]",
]);
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
        <div class="flex items-center px-4 py-3">
          <UButton
            icon="i-lucide-menu"
            color="neutral"
            variant="ghost"
            @click="uiStore.openMobile()"
          />
        </div>
      </div>

      <AppSidebar />

      <main :class="mainClass">
        <NuxtPage />
      </main>
    </div>
  </UApp>
</template>
