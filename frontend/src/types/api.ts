// Wire types — mirror the Pydantic DTOs in src/weftlyflow/server/schemas/.
// Kept deliberately close to the backend shape so translation is trivial.

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  display_name: string | null;
  global_role: string;
  default_project_id: string | null;
}

export interface WorkflowNode {
  id: string;
  name: string;
  type: string;
  type_version?: number;
  parameters?: Record<string, unknown>;
  credentials?: Record<string, string>;
  position?: [number, number];
  disabled?: boolean;
  notes?: string | null;
  continue_on_fail?: boolean;
}

export interface WorkflowConnection {
  source_node: string;
  target_node: string;
  source_port?: string;
  source_index?: number;
  target_port?: string;
  target_index?: number;
}

export interface WorkflowSettings {
  timezone?: string;
  timeout_seconds?: number;
  save_manual_executions?: boolean;
  save_trigger_executions_on?: string;
  error_workflow_id?: string | null;
  caller_policy?: string;
}

export interface Workflow {
  id: string;
  project_id: string;
  name: string;
  nodes: WorkflowNode[];
  connections: WorkflowConnection[];
  settings: WorkflowSettings;
  tags: string[];
  active: boolean;
  archived: boolean;
}

export interface WorkflowCreate {
  name: string;
  nodes?: WorkflowNode[];
  connections?: WorkflowConnection[];
  settings?: WorkflowSettings;
  tags?: string[];
}

export interface WorkflowUpdate extends WorkflowCreate {
  active?: boolean;
  archived?: boolean;
}

export interface ExecutionSummary {
  id: string;
  workflow_id: string;
  mode: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  triggered_by: string | null;
}

export interface ItemOut {
  json: Record<string, unknown>;
  binary?: Record<string, unknown>;
  error?: { message: string; code?: string } | null;
}

export interface NodeRunDataOut {
  items: ItemOut[][];
  execution_time_ms: number;
  started_at: string;
  status: "success" | "error" | "disabled";
  error?: { message: string; code?: string } | null;
}

export interface ExecutionDetail extends ExecutionSummary {
  run_data: Record<string, NodeRunDataOut[]>;
}

// --- Node-type catalog ------------------------------------------------------

export interface NodePropertyOption {
  value: string;
  label: string;
  description?: string | null;
}

export interface NodeProperty {
  name: string;
  display_name: string;
  type: string;
  default?: unknown;
  required?: boolean;
  description?: string | null;
  options?: NodePropertyOption[];
  placeholder?: string | null;
  type_options?: Record<string, unknown>;
}

export interface NodePort {
  name: string;
  kind: string;
  index: number;
  display_name?: string | null;
  required?: boolean;
}

export interface NodeCredentialSlot {
  name: string;
  credential_types: string[];
  required?: boolean;
}

export interface NodeType {
  type: string;
  version: number;
  display_name: string;
  description: string;
  icon: string;
  category: string;
  group: string[];
  inputs: NodePort[];
  outputs: NodePort[];
  credentials: NodeCredentialSlot[];
  properties: NodeProperty[];
  supports_binary?: boolean;
}

// --- Credentials -----------------------------------------------------------

export interface CredentialSummary {
  id: string;
  project_id: string;
  name: string;
  type: string;
  created_at: string;
  updated_at: string;
}

export interface CredentialCreate {
  name: string;
  type: string;
  data: Record<string, unknown>;
}

export interface CredentialUpdate {
  name: string;
  data: Record<string, unknown>;
}

export interface CredentialTestResult {
  ok: boolean;
  message: string;
}

export interface CredentialTypeEntry {
  slug: string;
  display_name: string;
  generic: boolean;
  properties: NodeProperty[];
}

// --- Errors -----------------------------------------------------------------

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface ApiErrorEnvelope {
  error: ApiError;
}
