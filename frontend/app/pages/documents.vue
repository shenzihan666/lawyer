<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useDocumentStore } from "../../stores/documents";

const store = useDocumentStore();
const { documents, stagedFiles, isLoading, isWorking } = storeToRefs(store);

const selectedRows = ref<Record<string, boolean>>({});
const selectedIds = computed(() => Object.keys(selectedRows.value));
const hasSelection = computed(() => selectedIds.value.length > 0);

const acceptedFormats = ".pdf,.doc,.docx,.xls,.xlsx";

const dateFormatter = computed(
  () =>
    new Intl.DateTimeFormat("zh-CN", {
      dateStyle: "medium",
      timeStyle: "short",
    }),
);

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return dateFormatter.value.format(new Date(value));
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  store.mergeFiles([...(input.files ?? [])]);
  input.value = "";
}

function onDrop(event: DragEvent) {
  store.mergeFiles([...(event.dataTransfer?.files ?? [])]);
}

const columns = [
  { accessorKey: "original_filename", header: "文档" },
  { accessorKey: "status", header: "状态" },
  { accessorKey: "meta", header: "元数据" },
  { id: "actions", header: "" },
];

const getStatusColor = (status: string) => {
  switch (status) {
    case "ready":
      return "success";
    case "failed":
      return "error";
    case "deleted":
      return "neutral";
    default:
      return "warning";
  }
};

const getStatusLabel = (status: string) => {
  switch (status) {
    case "ready":
      return "已加载";
    case "failed":
      return "失败";
    case "deleted":
      return "已删除";
    default:
      return "处理中";
  }
};

async function handleQueueVectorization(ids: string[]) {
  await store.queueVectorization(ids);
  selectedRows.value = {};
}

async function handleDelete(ids: string[]) {
  await store.deleteDocuments(ids);
  selectedRows.value = {};
}

onMounted(() => {
  store.refreshDocuments();
});
</script>

<template>
  <div class="space-y-6 bg-[#fcfbf8] px-4 py-4 md:px-8 md:py-8">
    <div
      class="rounded-[28px] border border-[#e8e3d9] bg-white px-6 py-5 shadow-[0_20px_60px_rgba(34,24,12,0.06)]"
    >
      <p class="text-xs uppercase tracking-[0.22em] text-zinc-400">
        Knowledge Base
      </p>
      <div
        class="mt-2 flex flex-col gap-2 md:flex-row md:items-end md:justify-between"
      >
        <div>
          <h1 class="text-2xl font-semibold tracking-tight text-zinc-950">
            知识库文档
          </h1>
          <p class="mt-1 text-sm text-zinc-500">
            上传、索引并管理用于 AI 对话的文档素材。
          </p>
        </div>
        <UBadge color="neutral" variant="subtle" size="lg"
          >PDF / Word / Excel</UBadge
        >
      </div>
    </div>

    <div class="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <UCard
        class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
      >
        <template #header>
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-base font-semibold text-zinc-900">导入区</h2>
              <p class="mt-1 text-sm text-zinc-500">
                支持拖拽和批量导入，适合作为知识库资料入口。
              </p>
            </div>
          </div>
        </template>

        <label
          class="block rounded-[24px] border-2 border-dashed border-zinc-200 px-6 py-12 text-center transition-colors hover:border-zinc-400 hover:bg-zinc-50/50"
          @dragover.prevent
          @drop.prevent="onDrop"
        >
          <input
            type="file"
            :accept="acceptedFormats"
            multiple
            class="hidden"
            @change="onFileChange"
          />
          <UIcon
            name="i-lucide-upload-cloud"
            class="mx-auto mb-4 h-10 w-10 text-zinc-400"
          />
          <p class="text-base font-medium text-zinc-900">
            点击或拖拽文件到此处
          </p>
          <p class="mt-2 text-sm text-zinc-500">支持一次导入多个文档</p>
        </label>

        <div v-if="stagedFiles.length" class="mt-5 space-y-3">
          <div
            v-for="file in stagedFiles"
            :key="`${file.name}-${file.lastModified}`"
            class="flex items-center justify-between rounded-2xl border border-zinc-100 bg-zinc-50 px-3 py-3"
          >
            <div class="flex min-w-0 items-center gap-3">
              <UIcon
                name="i-lucide-file-text"
                class="h-5 w-5 flex-shrink-0 text-zinc-400"
              />
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-zinc-700">
                  {{ file.name }}
                </p>
                <p class="text-xs text-zinc-500">
                  {{ formatFileSize(file.size) }}
                </p>
              </div>
            </div>
            <UButton
              icon="i-lucide-x"
              color="neutral"
              variant="ghost"
              size="xs"
              @click="store.removeStagedFile(file)"
            />
          </div>

          <div class="flex items-center justify-end gap-3 pt-2">
            <UButton
              color="neutral"
              variant="ghost"
              :disabled="isWorking"
              @click="store.clearStagedFiles()"
            >
              清空
            </UButton>
            <UButton
              color="primary"
              :loading="isWorking"
              @click="store.uploadDocuments()"
            >
              开始导入
            </UButton>
          </div>
        </div>
      </UCard>

      <UCard
        class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
      >
        <template #header>
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-base font-semibold text-zinc-900">文档索引</h2>
              <p class="mt-1 text-sm text-zinc-500">
                选择文档后可批量向量化或删除。
              </p>
            </div>
            <div class="flex items-center gap-2">
              <UButton
                icon="i-lucide-refresh-cw"
                color="neutral"
                variant="ghost"
                :loading="isLoading"
                @click="store.refreshDocuments()"
              />
              <template v-if="hasSelection">
                <UButton
                  color="primary"
                  variant="solid"
                  size="sm"
                  :loading="isWorking"
                  @click="handleQueueVectorization(selectedIds)"
                >
                  向量化 ({{ selectedIds.length }})
                </UButton>
                <UButton
                  color="error"
                  variant="soft"
                  size="sm"
                  :loading="isWorking"
                  @click="handleDelete(selectedIds)"
                >
                  删除
                </UButton>
              </template>
            </div>
          </div>
        </template>

        <UTable
          v-model:row-selection="selectedRows"
          :data="documents"
          :columns="columns"
          :loading="isLoading"
          class="w-full"
        >
          <template #original_filename-cell="{ row }">
            <div class="max-w-xs flex flex-col">
              <span
                class="truncate text-sm font-medium text-zinc-900"
                :title="(row.original as any).original_filename"
                >{{ (row.original as any).original_filename }}</span
              >
              <span
                class="mt-1 font-mono text-xs text-zinc-500"
                :title="(row.original as any).sha256"
                >{{ (row.original as any).sha256.slice(0, 12) }}...</span
              >
            </div>
          </template>

          <template #status-cell="{ row }">
            <div class="flex items-start space-y-1.5 flex-col">
              <UBadge
                :color="
                  getStatusColor((row.original as any).ingestion_status) as any
                "
                variant="subtle"
                size="xs"
              >
                {{ getStatusLabel((row.original as any).ingestion_status) }}
              </UBadge>
              <UBadge
                v-if="(row.original as any).vector_status === 'queued'"
                color="warning"
                variant="subtle"
                size="xs"
              >
                排队中
              </UBadge>
              <UBadge
                v-else-if="(row.original as any).vector_status === 'indexing'"
                color="warning"
                variant="subtle"
                size="xs"
              >
                索引中
              </UBadge>
              <UBadge
                v-else-if="(row.original as any).vector_status === 'indexed'"
                color="success"
                variant="subtle"
                size="xs"
              >
                已索引
              </UBadge>
              <UBadge
                v-else-if="(row.original as any).vector_status === 'failed'"
                color="error"
                variant="subtle"
                size="xs"
              >
                索引失败
              </UBadge>
            </div>
          </template>

          <template #meta-cell="{ row }">
            <div class="flex flex-col space-y-1 text-xs text-zinc-500">
              <span
                >{{ formatFileSize((row.original as any).file_size) }}
                &middot;
                {{
                  (row.original as any).file_extension === ".pdf"
                    ? `${(row.original as any).page_count}页`
                    : "无分页"
                }}</span
              >
              <span
                >上传于
                {{ formatDate((row.original as any).uploaded_at) }}</span
              >
            </div>
          </template>

          <template #actions-cell="{ row }">
            <div class="flex items-center justify-end space-x-2">
              <UButton
                color="primary"
                variant="ghost"
                icon="i-lucide-cpu"
                size="xs"
                :disabled="
                  isWorking ||
                  (row.original as any).ingestion_status !== 'ready' ||
                  ['queued', 'indexing', 'indexed'].includes(
                    (row.original as any).vector_status,
                  )
                "
                @click="handleQueueVectorization([(row.original as any).id])"
              />
              <UButton
                color="error"
                variant="ghost"
                icon="i-lucide-trash-2"
                size="xs"
                :disabled="isWorking"
                @click="handleDelete([(row.original as any).id])"
              />
            </div>
          </template>
        </UTable>
      </UCard>
    </div>
  </div>
</template>
