<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useDocumentStore } from "../../stores/documents";
import { useSearchStore } from "../../stores/search";

const documentStore = useDocumentStore();
const searchStore = useSearchStore();

const { documents, isLoading: isLoadingDocuments } = storeToRefs(documentStore);
const {
  hasSearched,
  isSearching,
  meta,
  query,
  results,
  selectedDocumentIds,
  topK,
} = storeToRefs(searchStore);

const indexedDocuments = computed(() =>
  documents.value.filter((item) => item.vector_status === "indexed"),
);

const candidateOptions = computed(() =>
  indexedDocuments.value.map((item) => ({
    label: item.original_filename,
    value: item.id,
  })),
);

const topKOptions = [3, 5, 8, 10].map((value) => ({
  label: `${value} 条`,
  value,
}));

const resultCountLabel = computed(() => `${results.value.length} 条结果`);

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
          Retrieval
        </p>
        <div
          class="mt-2 flex flex-col gap-2 md:flex-row md:items-end md:justify-between"
        >
          <div>
            <h1 class="text-2xl font-semibold tracking-tight text-zinc-950">
              智能检索
            </h1>
            <p class="mt-1 text-sm text-zinc-500">
              使用 Milvus 混合检索已索引文档，支持按文档范围过滤结果。
            </p>
          </div>
          <UBadge color="neutral" variant="subtle" size="lg">
            {{ indexedDocuments.length }} 个已索引文档
          </UBadge>
        </div>
      </div>

      <div class="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <UCard
          class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
        >
          <template #header>
            <div>
              <h2 class="text-base font-semibold text-zinc-900">检索参数</h2>
              <p class="mt-1 text-sm text-zinc-500">
                优先从已向量化的知识库文档中召回内容。
              </p>
            </div>
          </template>

          <div class="space-y-5">
            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700"
                >检索问题</label
              >
              <textarea
                v-model="query"
                rows="5"
                class="w-full rounded-2xl border border-[#e7e1d6] bg-[#fcfbf8] px-4 py-3 text-sm text-zinc-900 outline-none transition-colors placeholder:text-zinc-400 focus:border-zinc-400"
                placeholder="例如：合同违约责任一般如何认定？"
              />
            </div>

            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700"
                >返回数量</label
              >
              <USelect
                v-model="topK"
                :items="topKOptions"
                value-key="value"
                class="w-full"
              />
            </div>

            <div>
              <label class="mb-2 block text-sm font-medium text-zinc-700"
                >限制文档范围</label
              >
              <USelectMenu
                v-model="selectedDocumentIds"
                :items="candidateOptions"
                value-key="value"
                label-key="label"
                multiple
                searchable
                :loading="isLoadingDocuments"
                placeholder="默认搜索全部已索引文档"
                class="w-full"
              />
            </div>

            <div class="flex items-center gap-3 pt-2">
              <UButton
                color="neutral"
                variant="ghost"
                @click="searchStore.reset()"
              >
                清空结果
              </UButton>
              <UButton
                color="primary"
                :loading="isSearching"
                @click="searchStore.search()"
              >
                开始检索
              </UButton>
            </div>

            <div
              v-if="!indexedDocuments.length"
              class="rounded-2xl border border-dashed border-[#e7e1d6] bg-[#fcfbf8] px-4 py-4 text-sm text-zinc-500"
            >
              当前还没有已索引文档。先到“知识库”页面上传并执行向量化。
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
                <h2 class="text-base font-semibold text-zinc-900">检索结果</h2>
                <p class="mt-1 text-sm text-zinc-500">
                  自动显示召回模式、候选数和父块合并状态。
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <UBadge v-if="hasSearched" color="neutral" variant="subtle">
                  {{ resultCountLabel }}
                </UBadge>
                <UBadge
                  v-if="meta.retrieval_mode"
                  color="primary"
                  variant="subtle"
                >
                  {{ String(meta.retrieval_mode) }}
                </UBadge>
                <UBadge
                  v-if="meta.auto_merge_applied"
                  color="warning"
                  variant="subtle"
                >
                  自动合并 {{ Number(meta.auto_merge_replaced_chunks ?? 0) }} 条
                </UBadge>
              </div>
            </div>
          </template>

          <div
            v-if="!hasSearched"
            class="py-16 text-center text-sm text-zinc-400"
          >
            输入检索问题后，这里会显示命中的 chunk 内容。
          </div>

          <div
            v-else-if="!results.length"
            class="py-16 text-center text-sm text-zinc-400"
          >
            没有检索到结果，试试换个问题或放宽文档过滤条件。
          </div>

          <div v-else class="space-y-4">
            <div
              v-for="item in results"
              :key="item.chunk_id"
              class="rounded-[24px] border border-[#ece6dc] bg-[#fcfbf8] p-5"
            >
              <div
                class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between"
              >
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <p class="truncate text-sm font-semibold text-zinc-900">
                      {{ item.original_filename }}
                    </p>
                    <UBadge color="neutral" variant="subtle" size="xs">
                      L{{ item.chunk_level }} / #{{ item.chunk_index }}
                    </UBadge>
                    <UBadge
                      v-if="item.page_number"
                      color="neutral"
                      variant="subtle"
                      size="xs"
                    >
                      第 {{ item.page_number }} 页
                    </UBadge>
                  </div>
                  <p class="mt-1 text-xs text-zinc-500">
                    chunk_id: {{ item.chunk_id }}
                  </p>
                </div>

                <div class="flex items-center gap-2 text-xs text-zinc-500">
                  <span>score</span>
                  <span
                    class="rounded-full bg-white px-2 py-1 font-mono text-zinc-900 ring-1 ring-[#e7e1d6]"
                  >
                    {{ formatScore(item.score) }}
                  </span>
                </div>
              </div>

              <p
                class="mt-4 whitespace-pre-wrap text-sm leading-7 text-zinc-700"
              >
                {{ item.content }}
              </p>
            </div>
          </div>
        </UCard>
      </div>
    </div>
  </div>
</template>
