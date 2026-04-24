<script setup lang="ts">
// Workflow editor. Holds the edit state in memory; Save pushes the whole
// graph to the server via `PUT /api/v1/workflows/{id}`. Activate /
// Deactivate flip the backend-side trigger registrations.

import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import {
  type Connection as VueFlowConnection,
  type Edge,
  type Node as FlowNode,
  type NodeTypesObject,
  VueFlow,
  useVueFlow,
} from "@vue-flow/core";
import { MiniMap } from "@vue-flow/minimap";
import { ulid } from "ulidx";
import { computed, markRaw, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { extractErrorMessage } from "@/api/client";
import { workflows as workflowsApi } from "@/api/endpoints";
import WorkflowNodeCard from "@/components/canvas/WorkflowNodeCard.vue";
import ExecutionPanel from "@/components/ExecutionPanel.vue";
import NodeParameterForm from "@/components/NodeParameterForm.vue";
import NodePalette from "@/components/NodePalette.vue";
import Button from "@/components/ui/Button.vue";
import Dialog from "@/components/ui/Dialog.vue";
import Kbd from "@/components/ui/Kbd.vue";
import Separator from "@/components/ui/Separator.vue";
import Switch from "@/components/ui/Switch.vue";
import Tooltip from "@/components/ui/Tooltip.vue";
import { toast } from "@/lib/toast";
import { EDITOR_TOUR, startTour } from "@/lib/tour";
import { ArrowLeft, Keyboard, MousePointerClick } from "lucide-vue-next";
import { useCredentialsStore } from "@/stores/credentials";
import { useNodeTypesStore } from "@/stores/nodeTypes";
import type {
  ExecutionDetail,
  NodeType,
  Workflow,
  WorkflowConnection,
  WorkflowNode,
} from "@/types/api";

const props = defineProps<{ id: string }>();

const router = useRouter();
const nodeTypesStore = useNodeTypesStore();
const credentialsStore = useCredentialsStore();

const workflow = ref<Workflow | null>(null);
const nodes = reactive<WorkflowNode[]>([]);
const connections = reactive<WorkflowConnection[]>([]);
const selectedId = ref<string | null>(null);

const loading = ref(true);
const saving = ref(false);
const executing = ref(false);
const dirty = ref(false);
const executionError = ref<string | null>(null);
const execution = ref<ExecutionDetail | null>(null);
const activating = ref(false);

const flow = useVueFlow({ id: `editor-${props.id}` });

const paletteRef = ref<InstanceType<typeof NodePalette> | null>(null);
const shortcutsOpen = ref(false);

const nodeStatuses = computed<Record<string, "idle" | "success" | "error" | "running">>(() => {
  const out: Record<string, "idle" | "success" | "error" | "running"> = {};
  if (executing.value) {
    for (const n of nodes) {
      out[n.id] = "running";
    }
    return out;
  }
  const runData = execution.value?.run_data ?? {};
  for (const n of nodes) {
    const runs = runData[n.id];
    if (!runs || runs.length === 0) {
      out[n.id] = "idle";
      continue;
    }
    const last = runs[runs.length - 1];
    out[n.id] = last?.status === "error" ? "error" : "success";
  }
  return out;
});

const flowNodes = computed<FlowNode[]>(() =>
  nodes.map((n) => {
    const typeInfo = nodeTypesStore.lookup(n.type);
    return {
      id: n.id,
      type: "workflow",
      position: { x: n.position?.[0] ?? 0, y: n.position?.[1] ?? 0 },
      data: {
        label: n.name,
        slug: n.type,
        category: typeInfo?.category,
        status: nodeStatuses.value[n.id] ?? "idle",
        disabled: n.disabled,
      },
      selected: n.id === selectedId.value,
    };
  }),
);

const nodeTypes: NodeTypesObject = {
  workflow: markRaw(WorkflowNodeCard) as unknown as NodeTypesObject["workflow"],
};

const flowEdges = computed<Edge[]>(() =>
  connections.map((c, idx) => ({
    id: `${c.source_node}-${c.target_node}-${c.source_port ?? "main"}-${idx}`,
    source: c.source_node,
    target: c.target_node,
    sourceHandle: c.source_port ?? "main",
    targetHandle: c.target_port ?? "main",
  })),
);

const selectedNode = computed(() =>
  nodes.find((n) => n.id === selectedId.value) ?? null,
);

const selectedType = computed<NodeType | undefined>(() =>
  selectedNode.value ? nodeTypesStore.lookup(selectedNode.value.type) : undefined,
);

onMounted(async () => {
  await Promise.all([nodeTypesStore.loadOnce(), credentialsStore.fetchAll()]);
  await hydrateFromServer();
  loading.value = false;
  window.addEventListener("keydown", onGlobalKey);
  // Kick the editor walk-through on first visit (waits for panels to mount).
  setTimeout(() => startTour(EDITOR_TOUR), 500);
});

onBeforeUnmount(() => {
  // Drop any Vue Flow internal state so re-entering with the same id doesn't
  // leak the previous graph.
  flow.vueFlowRef.value = null;
  window.removeEventListener("keydown", onGlobalKey);
});

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

function onGlobalKey(event: KeyboardEvent): void {
  const meta = event.metaKey || event.ctrlKey;
  const editable = isEditableTarget(event.target);

  // Cmd/Ctrl+S → save
  if (meta && event.key.toLowerCase() === "s") {
    event.preventDefault();
    if (dirty.value && !saving.value) {
      void onSave();
    }
    return;
  }
  // Cmd/Ctrl+Enter → execute
  if (meta && event.key === "Enter") {
    event.preventDefault();
    if (!executing.value) {
      void onExecute();
    }
    return;
  }
  // Cmd/Ctrl+K → focus palette search
  if (meta && event.key.toLowerCase() === "k") {
    event.preventDefault();
    void paletteRef.value?.focusSearch();
    return;
  }
  // ? → open shortcuts cheatsheet (ignore when typing)
  if (!editable && event.key === "?") {
    event.preventDefault();
    shortcutsOpen.value = true;
    return;
  }
  // Delete / Backspace → remove selected node (ignore when typing)
  if (!editable && (event.key === "Delete" || event.key === "Backspace")) {
    if (selectedNode.value) {
      event.preventDefault();
      handleDeleteSelected();
    }
  }
}

async function hydrateFromServer(): Promise<void> {
  const fetched = await workflowsApi.get(props.id);
  workflow.value = fetched;
  nodes.splice(0, nodes.length, ...fetched.nodes.map((n) => ({ ...n })));
  connections.splice(0, connections.length, ...fetched.connections.map((c) => ({ ...c })));
  selectedId.value = nodes[0]?.id ?? null;
  dirty.value = false;
}

// --- Editing --------------------------------------------------------------

function markDirty(): void {
  dirty.value = true;
}

function handleAddNode(type: NodeType): void {
  const id = `node_${ulid()}`;
  const base = nodes[nodes.length - 1]?.position ?? [120, 160];
  const position: [number, number] = [base[0] + 220, base[1]];
  nodes.push({
    id,
    name: type.display_name,
    type: type.type,
    type_version: type.version,
    parameters: {},
    credentials: {},
    position,
    disabled: false,
    notes: null,
    continue_on_fail: false,
  });
  selectedId.value = id;
  markDirty();
}

function handleNodeSelect(id: string): void {
  selectedId.value = id;
}

function updateSelectedName(value: string): void {
  if (!selectedNode.value) {
    return;
  }
  selectedNode.value.name = value;
  markDirty();
}

function updateSelectedParameter(name: string, value: unknown): void {
  const node = selectedNode.value;
  if (!node) {
    return;
  }
  const params = { ...(node.parameters ?? {}) };
  if (value === null || value === undefined || value === "") {
    delete params[name];
  } else {
    params[name] = value;
  }
  node.parameters = params;
  markDirty();
}

function updateSelectedCredential(slot: string, credentialId: string | null): void {
  const node = selectedNode.value;
  if (!node) {
    return;
  }
  const creds = { ...(node.credentials ?? {}) };
  if (credentialId) {
    creds[slot] = credentialId;
  } else {
    delete creds[slot];
  }
  node.credentials = creds;
  markDirty();
}

function handleDeleteSelected(): void {
  const node = selectedNode.value;
  if (!node) {
    return;
  }
  const id = node.id;
  const keep = (c: WorkflowConnection) => c.source_node !== id && c.target_node !== id;
  const filtered = connections.filter(keep);
  connections.splice(0, connections.length, ...filtered);
  const remaining = nodes.filter((n) => n.id !== id);
  nodes.splice(0, nodes.length, ...remaining);
  selectedId.value = nodes[0]?.id ?? null;
  markDirty();
}

// --- Vue Flow events ------------------------------------------------------

function onNodesDragStop(event: { node: FlowNode }): void {
  const target = nodes.find((n) => n.id === event.node.id);
  if (!target) {
    return;
  }
  target.position = [event.node.position.x, event.node.position.y];
  markDirty();
}

function onConnect(params: VueFlowConnection): void {
  if (!params.source || !params.target) {
    return;
  }
  connections.push({
    source_node: params.source,
    target_node: params.target,
    source_port: params.sourceHandle ?? "main",
    target_port: params.targetHandle ?? "main",
    source_index: 0,
    target_index: 0,
  });
  markDirty();
}

function onPaneClick(): void {
  // Keep selection when the user clicks the empty pane.
}

// --- Persistence ----------------------------------------------------------

async function save(): Promise<Workflow> {
  if (!workflow.value) {
    throw new Error("workflow not loaded");
  }
  saving.value = true;
  try {
    const updated = await workflowsApi.update(workflow.value.id, {
      name: workflow.value.name,
      nodes: [...nodes],
      connections: [...connections],
      settings: workflow.value.settings,
      tags: workflow.value.tags,
      active: workflow.value.active,
      archived: workflow.value.archived,
    });
    workflow.value = updated;
    dirty.value = false;
    return updated;
  } finally {
    saving.value = false;
  }
}

async function onSave(): Promise<void> {
  try {
    await save();
    toast.success("Workflow saved");
  } catch (err) {
    const message = extractErrorMessage(err);
    executionError.value = message;
    toast.error("Save failed", message);
  }
}

async function onRename(value: string): Promise<void> {
  if (!workflow.value) {
    return;
  }
  workflow.value.name = value;
  markDirty();
}

async function onExecute(): Promise<void> {
  if (!workflow.value) {
    return;
  }
  executing.value = true;
  executionError.value = null;
  try {
    if (dirty.value) {
      await save();
    }
    execution.value = await workflowsApi.execute(workflow.value.id, [{}]);
    if (execution.value.status === "success") {
      toast.success("Execution finished");
    } else {
      toast.error("Execution failed", `Status: ${execution.value.status}`);
    }
  } catch (err) {
    const message = extractErrorMessage(err);
    executionError.value = message;
    toast.error("Execution failed", message);
  } finally {
    executing.value = false;
  }
}

async function onToggleActive(): Promise<void> {
  if (!workflow.value || activating.value) {
    return;
  }
  activating.value = true;
  executionError.value = null;
  try {
    if (dirty.value) {
      await save();
    }
    const next = !workflow.value.active;
    workflow.value = next
      ? await workflowsApi.activate(workflow.value.id)
      : await workflowsApi.deactivate(workflow.value.id);
    toast.success(next ? "Workflow activated" : "Workflow deactivated");
  } catch (err) {
    const message = extractErrorMessage(err);
    executionError.value = message;
    toast.error("Activation failed", message);
  } finally {
    activating.value = false;
  }
}

function onBack(): void {
  router.push({ name: "home" });
}

watch(
  () => workflow.value?.name,
  () => {
    /* nothing — header is bound directly */
  },
);
</script>

<template>
  <div class="editor">
    <header
      class="flex items-center gap-3 px-4 h-12 bg-[var(--color-surface)] border-b border-[var(--color-border-subtle)] shrink-0"
    >
      <Tooltip content="Back to workflows">
        <Button
          variant="ghost"
          size="icon"
          data-testid="editor-back"
          aria-label="Back to workflows"
          @click="onBack"
        >
          <ArrowLeft class="h-4 w-4" />
        </Button>
      </Tooltip>

      <Separator
        vertical
        inset
      />

      <input
        v-if="workflow"
        :value="workflow.name"
        data-testid="editor-name"
        placeholder="Untitled workflow"
        class="flex-1 max-w-[360px] bg-transparent border border-transparent rounded-[var(--radius-md)] px-2 py-1 text-[15px] font-semibold text-[var(--color-foreground)] placeholder:text-[var(--color-foreground-subtle)] hover:border-[var(--color-border-subtle)] focus:border-[var(--color-accent)] focus:outline-none transition-colors"
        @input="onRename(($event.target as HTMLInputElement).value)"
      >

      <span
        v-if="dirty"
        class="inline-flex items-center gap-1.5 text-[11px] text-[var(--color-warning)] italic"
      >
        <span class="h-1.5 w-1.5 rounded-full bg-[var(--color-warning)] animate-pulse" />
        unsaved changes
      </span>

      <div class="flex-1" />

      <Tooltip content="Save (⌘S)">
        <Button
          variant="default"
          size="sm"
          data-testid="editor-save"
          :loading="saving"
          :disabled="!dirty"
          @click="onSave"
        >
          {{ saving ? "Saving" : dirty ? "Save" : "Saved" }}
        </Button>
      </Tooltip>

      <Separator
        vertical
        inset
      />

      <div class="flex items-center gap-2">
        <span class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-foreground-subtle)]">
          {{ workflow?.active ? "Active" : "Inactive" }}
        </span>
        <Tooltip :content="workflow?.active ? 'Deactivate workflow' : 'Activate workflow'">
          <Switch
            data-testid="editor-toggle-active"
            :model-value="workflow?.active ?? false"
            :loading="activating"
            :aria-label="workflow?.active ? 'Deactivate workflow' : 'Activate workflow'"
            @update:model-value="() => onToggleActive()"
          />
        </Tooltip>
      </div>

      <Separator
        vertical
        inset
      />

      <Tooltip content="Keyboard shortcuts (?)">
        <Button
          variant="ghost"
          size="icon"
          aria-label="Keyboard shortcuts"
          data-testid="editor-shortcuts"
          @click="shortcutsOpen = true"
        >
          <Keyboard class="h-4 w-4" />
        </Button>
      </Tooltip>
    </header>

    <div
      v-if="loading"
      class="flex-1 flex flex-col"
      data-testid="editor-loading"
    >
      <div class="grid grid-cols-[260px_1fr_320px] flex-1 min-h-0">
        <div class="border-r border-[var(--color-border-subtle)] bg-[var(--color-surface)] p-3 space-y-2">
          <div class="h-8 w-full rounded-[var(--radius-md)] bg-[var(--color-surface-2)] animate-pulse" />
          <div
            v-for="i in 6"
            :key="i"
            class="h-10 w-full rounded-[var(--radius-md)] bg-[var(--color-surface-2)] animate-pulse"
          />
        </div>
        <div class="bg-[var(--color-bg)] flex items-center justify-center">
          <div class="flex flex-col items-center gap-3 text-[var(--color-foreground-subtle)]">
            <div class="h-10 w-10 rounded-full border-2 border-[var(--color-border-subtle)] border-t-[var(--color-accent)] animate-spin" />
            <span class="text-xs">Loading workflow…</span>
          </div>
        </div>
        <div class="border-l border-[var(--color-border-subtle)] bg-[var(--color-surface)] p-3 space-y-2">
          <div class="h-6 w-3/4 rounded-[var(--radius-sm)] bg-[var(--color-surface-2)] animate-pulse" />
          <div class="h-16 w-full rounded-[var(--radius-md)] bg-[var(--color-surface-2)] animate-pulse" />
          <div class="h-16 w-full rounded-[var(--radius-md)] bg-[var(--color-surface-2)] animate-pulse" />
        </div>
      </div>
    </div>

    <div
      v-else
      class="workspace"
    >
      <NodePalette
        ref="paletteRef"
        :types="nodeTypesStore.items"
        @select="handleAddNode"
      />

      <div class="canvas-area relative">
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
          :node-types="nodeTypes"
          :default-viewport="{ x: 0, y: 0, zoom: 1 }"
          fit-view-on-init
          @node-click="(e) => handleNodeSelect(e.node.id)"
          @node-drag-stop="onNodesDragStop"
          @connect="onConnect"
          @pane-click="onPaneClick"
        >
          <Background />
          <MiniMap />
          <Controls />
        </VueFlow>

        <div
          v-if="nodes.length === 0"
          class="pointer-events-none absolute inset-0 flex items-center justify-center"
          data-testid="canvas-empty-state"
        >
          <div class="pointer-events-auto flex flex-col items-center gap-3 rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface)]/80 backdrop-blur-sm px-8 py-6 text-center max-w-sm">
            <MousePointerClick class="h-8 w-8 text-[var(--color-accent)]" />
            <h3 class="text-sm font-semibold text-[var(--color-foreground)] m-0">
              Start by adding a node
            </h3>
            <p class="text-xs text-[var(--color-foreground-muted)] m-0">
              Pick a trigger from the palette on the left, or press
              <Kbd>⌘</Kbd> <Kbd>K</Kbd> to focus search.
            </p>
          </div>
        </div>

        <ExecutionPanel
          :execution="execution"
          :running="executing"
          :error-message="executionError"
          @run="onExecute"
        />
      </div>

      <aside class="inspector">
        <NodeParameterForm
          v-if="selectedNode"
          :node="selectedNode"
          :node-type="selectedType"
          :credentials="credentialsStore.items"
          @update-name="updateSelectedName"
          @update-parameter="updateSelectedParameter"
          @update-credential="updateSelectedCredential"
          @delete="handleDeleteSelected"
        />
        <div
          v-else
          class="flex flex-col items-center justify-center h-full p-6 text-center text-[var(--color-foreground-subtle)]"
        >
          <p class="text-sm m-0">
            Select a node to edit it.
          </p>
          <p class="text-xs mt-1 m-0">
            Click a node on the canvas or add one from the palette.
          </p>
        </div>
      </aside>
    </div>

    <Dialog
      v-model:open="shortcutsOpen"
      title="Keyboard shortcuts"
    >
      <ul class="flex flex-col divide-y divide-[var(--color-border-subtle)] text-sm">
        <li class="flex items-center justify-between py-2">
          <span class="text-[var(--color-foreground-muted)]">Save workflow</span>
          <span class="flex items-center gap-1"><Kbd>⌘</Kbd><Kbd>S</Kbd></span>
        </li>
        <li class="flex items-center justify-between py-2">
          <span class="text-[var(--color-foreground-muted)]">Execute workflow</span>
          <span class="flex items-center gap-1"><Kbd>⌘</Kbd><Kbd>Enter</Kbd></span>
        </li>
        <li class="flex items-center justify-between py-2">
          <span class="text-[var(--color-foreground-muted)]">Focus node search</span>
          <span class="flex items-center gap-1"><Kbd>⌘</Kbd><Kbd>K</Kbd></span>
        </li>
        <li class="flex items-center justify-between py-2">
          <span class="text-[var(--color-foreground-muted)]">Delete selected node</span>
          <span class="flex items-center gap-1"><Kbd>Delete</Kbd></span>
        </li>
        <li class="flex items-center justify-between py-2">
          <span class="text-[var(--color-foreground-muted)]">Show this cheatsheet</span>
          <span class="flex items-center gap-1"><Kbd>?</Kbd></span>
        </li>
      </ul>
      <p class="text-[11px] text-[var(--color-foreground-subtle)] mt-3 mb-0">
        On Windows / Linux, <Kbd>Ctrl</Kbd> replaces <Kbd>⌘</Kbd>.
      </p>
    </Dialog>
  </div>
</template>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: auto 1fr 320px;
}
.canvas-area {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.canvas-area :deep(.vue-flow) {
  flex: 1;
  background: var(--wf-bg);
}
.inspector {
  background: var(--wf-bg-elevated);
  border-left: 1px solid var(--wf-border);
  overflow-y: auto;
  min-width: 0;
}
</style>
