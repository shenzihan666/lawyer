<script setup lang="ts">
import { storeToRefs } from "pinia";
import { useDocumentStore } from "../../stores/documents";

const store = useDocumentStore();
const { documents, stagedFiles, isLoading, isWorking, vectorizationProgress } =
  storeToRefs(store);

type DocumentTab = "import" | "management";
type SelectionMap = Record<string, boolean>;

const activeTab = ref<DocumentTab>("import");
const tabs = [
  { key: "import", label: "导入文档", icon: "i-lucide-file-up" },
  { key: "management", label: "知识库管理", icon: "i-lucide-library-big" },
] as const;

const uploadSelectedRows = ref<SelectionMap>({});
const managementSelectedRows = ref<SelectionMap>({});
const indexedDocuments = computed(() =>
  documents.value.filter((item) => item.vector_status === "indexed"),
);
const unindexedDocuments = computed(() =>
  documents.value.filter((item) => item.vector_status !== "indexed"),
);
const uploadManagedDocuments = computed(() => [
  ...unindexedDocuments.value,
  ...indexedDocuments.value,
]);
const selectedUploadIds = computed(() =>
  uploadManagedDocuments.value
    .map((item) => item.id)
    .filter((id) => Boolean(uploadSelectedRows.value[id])),
);
const hasUploadSelection = computed(() => selectedUploadIds.value.length > 0);
const allUploadSelected = computed(
  () =>
    uploadManagedDocuments.value.length > 0 &&
    selectedUploadIds.value.length === uploadManagedDocuments.value.length,
);
const selectedManagementIds = computed(() =>
  indexedDocuments.value
    .map((item) => item.id)
    .filter((id) => Boolean(managementSelectedRows.value[id])),
);
const hasManagementSelection = computed(
  () => selectedManagementIds.value.length > 0,
);
const allManagementSelected = computed(
  () =>
    indexedDocuments.value.length > 0 &&
    selectedManagementIds.value.length === indexedDocuments.value.length,
);
const hasIndexedDocuments = computed(() => indexedDocuments.value.length > 0);
const hasUnindexedDocuments = computed(
  () => unindexedDocuments.value.length > 0,
);
const showVectorizationProgress = computed(
  () =>
    vectorizationProgress.value.active ||
    vectorizationProgress.value.percent > 0,
);
const trackedVectorizationDocuments = computed(() => {
  const trackedIds = new Set(vectorizationProgress.value.document_ids);
  return documents.value.filter((item) => trackedIds.has(item.id));
});

const acceptedFormats = ".pdf,.docx,.xls,.xlsx";

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

const uploadColumns = [
  { id: "select", header: "" },
  { accessorKey: "original_filename", header: "文档" },
  { accessorKey: "status", header: "状态" },
  { accessorKey: "meta", header: "元数据" },
  { id: "actions", header: "" },
];
const managementColumns = [
  { id: "select", header: "" },
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
  uploadSelectedRows.value = {};
}

async function handleDelete(ids: string[]) {
  await store.deleteDocuments(ids);
  uploadSelectedRows.value = {};
  managementSelectedRows.value = {};
}

function getDocumentRowId(row: any) {
  return row.id;
}

function selectDocumentIds(target: Ref<SelectionMap>, ids: string[]) {
  const nextSelected: SelectionMap = {};
  ids.forEach((id) => {
    nextSelected[id] = true;
  });
  target.value = nextSelected;
}

function toggleDocumentSelection(
  target: Ref<SelectionMap>,
  documentId: string,
  checked: boolean,
) {
  if (checked) {
    target.value = {
      ...target.value,
      [documentId]: true,
    };
    return;
  }

  const nextSelected = { ...target.value };
  delete nextSelected[documentId];
  target.value = nextSelected;
}

function selectAllDocuments() {
  selectDocumentIds(
    uploadSelectedRows,
    uploadManagedDocuments.value.map((item) => item.id),
  );
}

function selectAllUnindexedDocuments() {
  selectDocumentIds(
    uploadSelectedRows,
    unindexedDocuments.value.map((item) => item.id),
  );
}

function clearUploadSelectedDocuments() {
  uploadSelectedRows.value = {};
}

function clearManagementSelectedDocuments() {
  managementSelectedRows.value = {};
}

function selectAllIndexedDocuments() {
  selectDocumentIds(
    managementSelectedRows,
    indexedDocuments.value.map((item) => item.id),
  );
}

function toggleUploadDocumentSelection(documentId: string, checked: boolean) {
  toggleDocumentSelection(uploadSelectedRows, documentId, checked);
}

function toggleManagementDocumentSelection(
  documentId: string,
  checked: boolean,
) {
  toggleDocumentSelection(managementSelectedRows, documentId, checked);
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

    <div
      class="inline-flex w-full flex-wrap gap-2 rounded-[24px] border border-[#e8e3d9] bg-white/85 p-2 shadow-[0_16px_45px_rgba(34,24,12,0.04)]"
      role="tablist"
      aria-label="知识库标签"
    >
      <button
        v-for="tab in tabs"
        :key="tab.key"
        type="button"
        class="inline-flex items-center gap-2 rounded-[18px] px-4 py-2.5 text-sm font-medium transition-all"
        :class="
          activeTab === tab.key
            ? 'bg-zinc-950 text-white shadow-[0_14px_28px_rgba(24,24,27,0.18)]'
            : 'text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900'
        "
        @click="activeTab = tab.key"
      >
        <UIcon :name="tab.icon" class="h-4 w-4" />
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <div
      v-if="activeTab === 'import'"
      class="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]"
    >
      <UCard
        class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
      >
        <template #header>
          <div class="flex items-center justify-between">
            <div>
              <h2 class="text-base font-semibold text-zinc-900">导入文档</h2>
              <p class="mt-1 text-sm text-zinc-500">支持拖拽和批量导入。</p>
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
          <div
            class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between"
          >
            <div>
              <h2 class="text-base font-semibold text-zinc-900">上传管理</h2>
              <p class="mt-1 text-sm text-zinc-500">
                所有上传文件都在这里，未索引文档优先显示，已索引文档排在下方。
              </p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
              <UButton
                icon="i-lucide-refresh-cw"
                color="neutral"
                variant="ghost"
                :loading="isLoading"
                @click="store.refreshDocuments()"
              />
              <UButton
                color="primary"
                variant="soft"
                size="sm"
                :disabled="!hasUnindexedDocuments"
                @click="selectAllUnindexedDocuments()"
              >
                一键全选未索引
              </UButton>
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                :disabled="!uploadManagedDocuments.length || allUploadSelected"
                @click="selectAllDocuments()"
              >
                一键全选
              </UButton>
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                :disabled="!hasUploadSelection"
                @click="clearUploadSelectedDocuments()"
              >
                一键取消全选
              </UButton>
              <UBadge color="neutral" variant="subtle" size="sm">
                已选 {{ selectedUploadIds.length }} /
                {{ uploadManagedDocuments.length }}
              </UBadge>
              <template v-if="hasUploadSelection">
                <UButton
                  color="primary"
                  variant="solid"
                  size="sm"
                  :loading="isWorking"
                  @click="handleQueueVectorization(selectedUploadIds)"
                >
                  向量化 ({{ selectedUploadIds.length }})
                </UButton>
                <UButton
                  color="error"
                  variant="soft"
                  size="sm"
                  :loading="isWorking"
                  @click="handleDelete(selectedUploadIds)"
                >
                  删除
                </UButton>
              </template>
            </div>
          </div>
        </template>

        <div
          v-if="showVectorizationProgress"
          class="mb-5 rounded-[24px] border border-[#ece4d6] bg-[#fbf6ed] px-4 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]"
        >
          <div
            class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"
          >
            <div>
              <div class="flex items-center gap-2">
                <span class="text-sm font-semibold text-zinc-900">
                  Indexing progress
                </span>
                <UBadge color="neutral" variant="subtle" size="xs">
                  {{ vectorizationProgress.completed }} /
                  {{ vectorizationProgress.total }} docs
                </UBadge>
              </div>
              <p class="mt-1 text-sm text-zinc-600">
                {{ vectorizationProgress.label }}
              </p>
            </div>
            <div class="text-left md:text-right">
              <p class="text-2xl font-semibold tracking-tight text-zinc-950">
                {{ vectorizationProgress.percent }}%
              </p>
              <p class="text-xs text-zinc-500">
                {{ vectorizationProgress.indexed }} indexed ·
                {{ vectorizationProgress.failed }} failed ·
                {{
                  vectorizationProgress.indexing + vectorizationProgress.queued
                }}
                active
              </p>
            </div>
          </div>

          <div
            class="mt-4 h-2 overflow-hidden rounded-full bg-white ring-1 ring-[#eadfce]"
          >
            <div
              class="h-full rounded-full bg-gradient-to-r from-amber-500 via-orange-500 to-emerald-500 transition-all duration-500 ease-out"
              :style="{ width: `${vectorizationProgress.percent}%` }"
            />
          </div>

          <div
            v-if="trackedVectorizationDocuments.length"
            class="mt-3 flex flex-wrap gap-2"
          >
            <UBadge
              v-for="item in trackedVectorizationDocuments"
              :key="item.id"
              color="neutral"
              variant="subtle"
              size="xs"
            >
              {{ item.original_filename }}
              <span class="ml-1 text-zinc-500">{{ item.vector_status }}</span>
            </UBadge>
          </div>
        </div>

        <UTable
          v-model:row-selection="uploadSelectedRows"
          :data="uploadManagedDocuments"
          :columns="uploadColumns"
          :get-row-id="getDocumentRowId"
          :loading="isLoading"
          class="w-full"
        >
          <template #select-header>
            <div class="flex justify-center">
              <UCheckbox
                :model-value="allUploadSelected"
                :indeterminate="hasUploadSelection && !allUploadSelected"
                @update:model-value="
                  ($event) =>
                    $event
                      ? selectAllDocuments()
                      : clearUploadSelectedDocuments()
                "
              />
            </div>
          </template>

          <template #select-cell="{ row }">
            <div class="flex justify-center">
              <UCheckbox
                :model-value="
                  uploadSelectedRows[(row.original as any).id] === true
                "
                @update:model-value="
                  ($event) =>
                    toggleUploadDocumentSelection(
                      (row.original as any).id,
                      !!$event,
                    )
                "
              />
            </div>
          </template>

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

    <UCard
      v-else
      class="rounded-[28px] ring-1 ring-[#ebe5da] shadow-[0_20px_60px_rgba(34,24,12,0.05)]"
    >
      <template #header>
        <div
          class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between"
        >
          <div>
            <h2 class="text-base font-semibold text-zinc-900">知识库管理</h2>
            <p class="mt-1 text-sm text-zinc-500">
              这里展示所有已经完成索引、可用于知识库检索的文档。
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <UBadge color="success" variant="subtle" size="sm">
              已索引 {{ indexedDocuments.length }}
            </UBadge>
            <UButton
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="ghost"
              :loading="isLoading"
              @click="store.refreshDocuments()"
            />
            <UButton
              color="neutral"
              variant="ghost"
              size="sm"
              :disabled="!indexedDocuments.length || allManagementSelected"
              @click="selectAllIndexedDocuments()"
            >
              一键全选
            </UButton>
            <UButton
              color="neutral"
              variant="ghost"
              size="sm"
              :disabled="!hasManagementSelection"
              @click="clearManagementSelectedDocuments()"
            >
              一键取消全选
            </UButton>
            <template v-if="hasManagementSelection">
              <UBadge color="neutral" variant="subtle" size="sm">
                已选 {{ selectedManagementIds.length }} /
                {{ indexedDocuments.length }}
              </UBadge>
              <UButton
                color="error"
                variant="soft"
                size="sm"
                :loading="isWorking"
                @click="handleDelete(selectedManagementIds)"
              >
                删除所选
              </UButton>
            </template>
          </div>
        </div>
      </template>

      <div
        v-if="!hasIndexedDocuments && !isLoading"
        class="rounded-[24px] border border-dashed border-zinc-200 bg-zinc-50/80 px-6 py-14 text-center"
      >
        <UIcon
          name="i-lucide-library-big"
          class="mx-auto mb-3 h-10 w-10 text-zinc-300"
        />
        <p class="text-base font-medium text-zinc-900">还没有已索引文档</p>
        <p class="mt-2 text-sm text-zinc-500">
          先去“导入文档”上传文件并完成索引，这里就会自动显示。
        </p>
      </div>

      <UTable
        v-else
        v-model:row-selection="managementSelectedRows"
        :data="indexedDocuments"
        :columns="managementColumns"
        :get-row-id="getDocumentRowId"
        :loading="isLoading"
        class="w-full"
      >
        <template #select-header>
          <div class="flex justify-center">
            <UCheckbox
              :model-value="allManagementSelected"
              :indeterminate="hasManagementSelection && !allManagementSelected"
              @update:model-value="
                ($event) =>
                  $event
                    ? selectAllIndexedDocuments()
                    : clearManagementSelectedDocuments()
              "
            />
          </div>
        </template>

        <template #select-cell="{ row }">
          <div class="flex justify-center">
            <UCheckbox
              :model-value="
                managementSelectedRows[(row.original as any).id] === true
              "
              @update:model-value="
                ($event) =>
                  toggleManagementDocumentSelection(
                    (row.original as any).id,
                    !!$event,
                  )
              "
            />
          </div>
        </template>

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
          <div class="flex flex-col items-start space-y-1.5">
            <UBadge
              :color="
                getStatusColor((row.original as any).ingestion_status) as any
              "
              variant="subtle"
              size="xs"
            >
              {{ getStatusLabel((row.original as any).ingestion_status) }}
            </UBadge>
            <UBadge color="success" variant="subtle" size="xs">已索引</UBadge>
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
              >上传于 {{ formatDate((row.original as any).uploaded_at) }}</span
            >
          </div>
        </template>

        <template #actions-cell="{ row }">
          <div class="flex items-center justify-end space-x-2">
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
</template>
