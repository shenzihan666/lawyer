import { defineStore } from "pinia";

export const useUiStore = defineStore("ui", () => {
  const isMobileOpen = ref(false);

  function openMobile() {
    isMobileOpen.value = true;
  }

  function closeMobile() {
    isMobileOpen.value = false;
  }

  return {
    isMobileOpen,
    openMobile,
    closeMobile,
  };
});
