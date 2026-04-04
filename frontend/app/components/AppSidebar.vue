<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useUiStore } from "../../stores/ui";

const uiStore = useUiStore();
const { isMobileOpen, isSidebarCollapsed } = storeToRefs(uiStore);
const route = useRoute();

const navItems = [
  { label: "新对话", path: "/", icon: "i-lucide-pencil-line" },
  { label: "知识库", path: "/documents", icon: "i-lucide-book-open" },
  { label: "智能检索", path: "/search", icon: "i-lucide-search" },
  {
    label: "更多",
    icon: "i-lucide-layout-grid",
    trailingIcon: "i-lucide-chevron-right",
  },
];

const shellClass = computed(() => [
  "fixed inset-y-0 left-0 z-40 transition-transform duration-300",
  isMobileOpen.value ? "translate-x-0" : "-translate-x-full",
  isSidebarCollapsed.value ? "md:-translate-x-full" : "md:translate-x-0",
]);

function isActive(path: string) {
  return route.path === path;
}

function handleNavigate() {
  uiStore.closeMobile();
}
</script>

<template>
  <div
    v-if="isMobileOpen"
    class="fixed inset-0 z-30 bg-zinc-950/20 backdrop-blur-sm md:hidden"
    @click="uiStore.closeMobile()"
  />

  <div :class="shellClass">
    <aside
      class="flex h-full w-[264px] flex-col border-r border-[#ebe5da] bg-[#f7f4ee] shadow-xl shadow-zinc-950/5 md:shadow-none"
    >
      <div class="flex items-center justify-end px-4 pb-4 pt-6">
        <UButton
          class="hidden md:inline-flex"
          icon="i-lucide-panel-left-close"
          color="neutral"
          variant="ghost"
          @click="uiStore.toggleSidebar()"
        />

        <UButton
          class="md:hidden"
          icon="i-lucide-x"
          color="neutral"
          variant="ghost"
          @click="uiStore.closeMobile()"
        />
      </div>

      <nav class="space-y-1 px-3 py-3">
        <template v-for="item in navItems" :key="item.label">
          <NuxtLink
            v-if="item.path"
            :to="item.path"
            class="flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-[15px] transition-colors"
            :class="
              isActive(item.path)
                ? 'bg-[#eef2ff] text-[#3158ff] ring-1 ring-[#d9e1ff]'
                : 'text-zinc-800 hover:bg-white/70'
            "
            @click="handleNavigate()"
          >
            <UIcon :name="item.icon" class="h-5 w-5 flex-shrink-0" />
            <span class="truncate">{{ item.label }}</span>
          </NuxtLink>

          <button
            v-else
            type="button"
            class="flex w-full items-center justify-between rounded-2xl px-3 py-3 text-left text-[15px] text-zinc-800 transition-colors hover:bg-white/70"
            @click="handleNavigate()"
          >
            <div class="flex min-w-0 items-center gap-3">
              <UIcon :name="item.icon" class="h-5 w-5 flex-shrink-0" />
              <span class="truncate">{{ item.label }}</span>
            </div>
            <UIcon
              v-if="item.trailingIcon"
              :name="item.trailingIcon"
              class="h-4 w-4 flex-shrink-0 text-zinc-400"
            />
          </button>
        </template>
      </nav>
    </aside>
  </div>
</template>
