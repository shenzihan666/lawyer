<script setup lang="ts">
import { useUiStore } from "../../stores/ui";

const uiStore = useUiStore();
const draft = ref("");
</script>

<template>
  <div class="flex min-h-screen flex-col bg-[#fcfbf8]">
    <header
      class="relative flex items-center border-b border-[#ebe5da] px-4 py-4 md:px-5"
    >
      <div class="flex items-center gap-2 text-zinc-900">
        <button
          class="rounded-xl p-2 transition-colors hover:bg-white"
          @click="uiStore.toggleSidebar()"
        >
          <UIcon name="i-lucide-panels-left-right" class="h-5 w-5" />
        </button>
        <button class="rounded-xl p-2 transition-colors hover:bg-white">
          <UIcon name="i-lucide-pencil-line" class="h-5 w-5" />
        </button>
      </div>

      <div
        class="pointer-events-none absolute inset-x-0 hidden text-center md:block"
      >
        <h1 class="text-base font-semibold text-zinc-950">新对话</h1>
      </div>
    </header>

    <section
      class="flex flex-1 flex-col justify-center px-4 pb-6 pt-14 md:px-10 md:pb-10 md:pt-24"
    >
      <div class="flex-1" />

      <div class="mx-auto mt-10 w-full max-w-4xl">
        <div
          class="rounded-[28px] border border-[#e7e1d6] bg-white px-5 pb-4 pt-4 shadow-[0_20px_60px_rgba(34,24,12,0.08)]"
        >
          <textarea
            v-model="draft"
            rows="2"
            class="min-h-[64px] w-full resize-none border-0 bg-transparent text-base text-zinc-900 outline-none placeholder:text-zinc-400"
            placeholder="发消息或输入 '/' 选择技能"
          />

          <div
            class="mt-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between"
          >
            <div class="flex items-center gap-4 text-sm text-zinc-800">
              <button
                class="rounded-xl p-1.5 transition-colors hover:bg-zinc-100"
              >
                <UIcon name="i-lucide-paperclip" class="h-5 w-5" />
              </button>
            </div>

            <button
              class="ml-auto flex h-10 w-10 items-center justify-center rounded-full bg-[#f2f1ef] text-zinc-900 transition-colors hover:bg-[#ebe8e3]"
            >
              <UIcon name="i-lucide-mic" class="h-4.5 w-4.5" />
            </button>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
