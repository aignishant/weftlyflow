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
  VueFlow,
  useVueFlow,
} from "@vue-flow/core";
import { MiniMap } from "@vue-flow/minimap";
import { ulid } from "ulidx";
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { extractErrorMessage } from "@/api/client";
import { workflows as workflowsApi } from "@/api/endpoints";
import ExecutionPanel from "@/components/ExecutionPanel.vue";
import NodeParameterForm from "@/components/NodeParameterForm.vue";
import NodePalette from "@/components/NodePalette.vue";
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

const flowNodes = computed<FlowNode[]>(() =>
  nodes.map((n) => ({
    id: n.id,
    type: "default",
    position: { x: n.position?.[0] ?? 0, y: n.position?.[1] ?? 0 },
    data: { label: n.name, slug: n.type },
    selected: n.id === selectedId.value,
  })),
);

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
});

onBeforeUnmount(() => {
  // Drop any Vue Flow internal state so re-entering with the same id doesn't
  // leak the previous graph.
  flow.vueFlowRef.value = null;
});

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
  } catch (err) {
    executionError.value = extractErrorMessage(err);
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
  } catch (err) {
    executionError.value = extractErrorMessage(err);
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
  } catch (err) {
    executionError.value = extractErrorMessage(err);
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
    <header class="editor-header">
      <button data-testid="editor-back" @click="onBack">← Back</button>
      <input
        v-if="workflow"
        :value="workflow.name"
        data-testid="editor-name"
        @input="onRename(($event.target as HTMLInputElement).value)"
      />
      <span class="wf-badge" :class="workflow?.active ? 'success' : 'waiting'">
        {{ workflow?.active ? "active" : "inactive" }}
      </span>
      <div class="spacer" />
      <button
        data-testid="editor-save"
        :disabled="saving || !dirty"
        @click="onSave"
      >
        {{ saving ? "Saving…" : dirty ? "Save" : "Saved" }}
      </button>
      <button
        data-testid="editor-toggle-active"
        :disabled="activating"
        @click="onToggleActive"
      >
        {{ workflow?.active ? "Deactivate" : "Activate" }}
      </button>
    </header>

    <div v-if="loading" class="loading">Loading workflow…</div>

    <div v-else class="workspace">
      <NodePalette :types="nodeTypesStore.items" @select="handleAddNode" />

      <div class="canvas-area">
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
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
        <p v-else class="empty">Select a node to edit it.</p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.editor-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--wf-bg-elevated);
  border-bottom: 1px solid var(--wf-border);
  flex: 0 0 auto;
}
.editor-header input {
  flex: 0 1 320px;
  background: transparent;
  border: 1px solid transparent;
  font-weight: 600;
  font-size: 15px;
}
.editor-header input:focus {
  border-color: var(--wf-border);
}
.editor-header .spacer {
  flex: 1;
}
.loading {
  padding: 40px;
  color: var(--wf-text-muted);
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
.empty {
  padding: 24px;
  color: var(--wf-text-muted);
}
</style>
