<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useChatStore } from "../../stores/chat";
import { useDocumentStore } from "../../stores/documents";

const chatStore = useChatStore();
const documentStore = useDocumentStore();

const { documents, isLoading: isLoadingDocuments } = storeToRefs(documentStore);
const {
  answer,
  citations,
  hasAnswered,
  isResponding,
  meta,
  prompt,
  selectedDocumentIds,
  topK,
} = storeToRefs(chatStore);

const indexedDocuments = computed(() =>
  documents.value.filter((item) => item.vector_status === "indexed"),
);

const candidateOptions = computed(() =>
  indexedDocuments.value.map((item) => ({
    label: item.original_filename,
    value: item.id,
  })),
);

const topKOptions = [3, 5, 8].map((value) => ({
  label: `${value} 条来源`,
  value,
}));

const citationCountLabel = computed(() => `${citations.value.length} 条引用`);

function formatScore(score: number) {
  return score.toFixed(3);
}

onMounted(() => {
  if (!documents.value.length) {
    documentStore.refreshDocuments();
  }
});
</script>

<template>
  <div class="min-h-screen bg-[#fcfbf8] px-4 py-6 md:px-8 md:py-8">
    <div class="mx-auto max-w-6xl space-y-6">
      <div
        class="rounded-[28px] border border-[#e8e1d6] bg-white px-6 py-6 shadow-[0_20px_60px_rgba(34,24,12,0.06)]"
      >
        <p class="text-xs uppercase tracking-[0.22em] text-zinc-400">
          Grounded Answer
        </p>
        <div
          class="mt-2 flex flex-col gap-2 md:flex-row md:items-end md:justify-between"
        >
          <div>
            <h1 class="text-2xl font-semibold tracking-tight text-zinc-950">
              对话助手
            </h1>
            <p class="mt-1 text-sm text-zinc-500">
              基于已索引文档生成法律问答，并给出可追溯的引用依据。
            </p>
          </div>
          <UBadge color="neutral" variant="subtle" size="lg">
            {{ indexedDocuments.length }} 个可用文档
          </UBadge>
        </div>
      </div>

      <div class="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <UCard
          class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
        >
          <template #header>
            <div>
              <h2 class="text-base font-semibold text-zinc-900">提问设置</h2>
              <p class="mt-1 text-sm text-zinc-500">
                支持按文档范围过滤，并控制回答时参考的来源数量。
              </p>
            </div>
          </template>

          <div class="space-y-5">
            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700">
                法律问题
              </label>
              <textarea
                v-model="prompt"
                rows="6"
                class="w-full rounded-2xl border border-[#e7e1d6] bg-[#fcfbf8] px-4 py-3 text-sm text-zinc-900 outline-none transition-colors placeholder:text-zinc-400 focus:border-zinc-400"
                placeholder="例如：房屋被他人占有时，我应该如何主张返还原物？"
              />
            </div>

            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700">
                参考来源数量
              </label>
              <USelect
                v-model="topK"
                :items="topKOptions"
                value-key="value"
                class="w-full"
              />
            </div>

            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700">
                限制文档范围
              </label>
              <USelectMenu
                v-model="selectedDocumentIds"
                :items="candidateOptions"
                value-key="value"
                label-key="label"
                multiple
                searchable
                :loading="isLoadingDocuments"
                placeholder="默认检索全部已索引文档"
                class="w-full"
              />
            </div>

            <div class="flex items-center gap-3 pt-2">
              <UButton color="neutral" variant="ghost" @click="chatStore.reset()">
                清空回答
              </UButton>
              <UButton
                color="primary"
                :loading="isResponding"
                @click="chatStore.ask()"
              >
                开始问答
              </UButton>
            </div>

            <div
              v-if="!indexedDocuments.length"
              class="rounded-2xl border border-dashed border-[#e7e1d6] bg-[#fcfbf8] px-4 py-4 text-sm text-zinc-500"
            >
              当前还没有已索引文档。请先在“知识库”页面上传并完成向量化。
            </div>
          </div>
        </UCard>

        <UCard
          class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
        >
          <template #header>
            <div
              class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
            >
              <div>
                <h2 class="text-base font-semibold text-zinc-900">回答结果</h2>
                <p class="mt-1 text-sm text-zinc-500">
                  回答中的 [1][2] 编号与下方引用卡片一一对应。
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <UBadge v-if="hasAnswered" color="neutral" variant="subtle">
                  {{ citationCountLabel }}
                </UBadge>
                <UBadge
                  v-if="meta.generation_mode"
                  color="primary"
                  variant="subtle"
                >
                  {{ String(meta.generation_mode) }}
                </UBadge>
                <UBadge
                  v-if="meta.grounding_status"
                  color="warning"
                  variant="subtle"
                >
                  {{ String(meta.grounding_status) }}
                </UBadge>
              </div>
            </div>
          </template>

          <div
            v-if="!hasAnswered"
            class="py-16 text-center text-sm text-zinc-400"
          >
            输入问题后，这里会生成基于文档依据的回答与引用。
          </div>

          <div v-else class="space-y-6">
            <div class="rounded-[24px] border border-[#ece6dc] bg-[#fcfbf8] p-5">
              <p class="text-xs uppercase tracking-[0.2em] text-zinc-400">Answer</p>
              <p
                class="mt-3 whitespace-pre-wrap text-sm leading-7 text-zinc-700"
              >
                {{ answer }}
              </p>
            </div>

            <div
              v-if="meta.answer_generation_skipped_reason"
              class="rounded-2xl border border-[#eadfcb] bg-[#fff8ec] px-4 py-3 text-sm text-[#8a5a14]"
            >
              当前为兜底模式：
              {{ String(meta.answer_generation_skipped_reason) }}
            </div>

            <div class="space-y-4">
              <div
                v-for="citation in citations"
                :key="citation.chunk_id"
                class="rounded-[24px] border border-[#ece6dc] bg-white p-5"
              >
                <div
                  class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between"
                >
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <UBadge color="primary" variant="subtle" size="xs">
                        [{{ citation.citation_number }}]
                      </UBadge>
                      <p class="truncate text-sm font-semibold text-zinc-900">
                        {{ citation.original_filename }}
                      </p>
                      <UBadge color="neutral" variant="subtle" size="xs">
                        L{{ citation.chunk_level }} / #{{ citation.chunk_index }}
                      </UBadge>
                      <UBadge color="neutral" variant="subtle" size="xs">
                        第 {{ citation.page_number || 0 }} 页
                      </UBadge>
                    </div>
                    <p class="mt-1 text-xs text-zinc-500">
                      chunk_id: {{ citation.chunk_id }}
                    </p>
                  </div>

                  <div class="flex items-center gap-2 text-xs text-zinc-500">
                    <span>score</span>
                    <span
                      class="rounded-full bg-[#fcfbf8] px-2 py-1 font-mono text-zinc-900 ring-1 ring-[#e7e1d6]"
                    >
                      {{ formatScore(citation.score) }}
                    </span>
                  </div>
                </div>

                <p
                  class="mt-4 whitespace-pre-wrap text-sm leading-7 text-zinc-700"
                >
                  {{ citation.snippet }}
                </p>
              </div>
            </div>
          </div>
        </UCard>
      </div>
    </div>
  </div>
</template>
