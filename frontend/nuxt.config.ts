// https://nuxt.com/docs/api/configuration/nuxt-config
const mainCss = decodeURIComponent(
  new URL("./app/assets/css/main.css", import.meta.url).pathname,
);

export default defineNuxtConfig({
  compatibilityDate: "2025-07-15",
  ssr: false,
  devtools: { enabled: true },
  css: [mainCss],
  modules: ["@nuxt/ui", "@pinia/nuxt"],
  fonts: {
    providers: {
      google: false,
      googleicons: false,
    },
    provider: "local",
  },
  icon: {
    serverBundle: {
      collections: ["lucide", "heroicons"],
    },
  },
  imports: {
    dirs: ["stores"],
  },
  runtimeConfig: {
    public: {
      apiBase: "http://127.0.0.1:8000/api/v1",
    },
  },
});
