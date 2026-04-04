import { defineStore } from "pinia";

export const useUiStore = defineStore("ui", () => {
  const isMobileOpen = ref(false);
  const isSidebarCollapsed = ref(false);

  function openMobile() {
    isMobileOpen.value = true;
  }

  function closeMobile() {
    isMobileOpen.value = false;
  }

  function toggleSidebar() {
    isSidebarCollapsed.value = !isSidebarCollapsed.value;
  }

  return {
    isMobileOpen,
    isSidebarCollapsed,
    openMobile,
    closeMobile,
    toggleSidebar,
  };
});
