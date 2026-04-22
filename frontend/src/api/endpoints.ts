// Resource-grouped API functions. Each resource is a plain object so call
// sites read like `workflows.list()` / `credentials.test(id)`.

import { api } from "@/api/client";
import type {
  CredentialCreate,
  CredentialSummary,
  CredentialTestResult,
  CredentialTypeEntry,
  CredentialUpdate,
  ExecutionDetail,
  ExecutionSummary,
  LoginResponse,
  NodeType,
  UserResponse,
  Workflow,
  WorkflowCreate,
  WorkflowUpdate,
} from "@/types/api";

export const auth = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const { data } = await api.post<LoginResponse>("/api/v1/auth/login", {
      email,
      password,
    });
    return data;
  },
  async me(): Promise<UserResponse> {
    const { data } = await api.get<UserResponse>("/api/v1/auth/me");
    return data;
  },
  async logout(): Promise<void> {
    await api.post("/api/v1/auth/logout").catch(() => {
      // Server-side revocation is best-effort; the client clears state regardless.
    });
  },
};

export const workflows = {
  async list(): Promise<Workflow[]> {
    const { data } = await api.get<Workflow[]>("/api/v1/workflows");
    return data;
  },
  async get(id: string): Promise<Workflow> {
    const { data } = await api.get<Workflow>(`/api/v1/workflows/${id}`);
    return data;
  },
  async create(body: WorkflowCreate): Promise<Workflow> {
    const { data } = await api.post<Workflow>("/api/v1/workflows", body);
    return data;
  },
  async update(id: string, body: WorkflowUpdate): Promise<Workflow> {
    const { data } = await api.put<Workflow>(`/api/v1/workflows/${id}`, body);
    return data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/api/v1/workflows/${id}`);
  },
  async activate(id: string): Promise<Workflow> {
    const { data } = await api.post<Workflow>(`/api/v1/workflows/${id}/activate`);
    return data;
  },
  async deactivate(id: string): Promise<Workflow> {
    const { data } = await api.post<Workflow>(`/api/v1/workflows/${id}/deactivate`);
    return data;
  },
  async execute(id: string, initialItems: Record<string, unknown>[]): Promise<ExecutionDetail> {
    const { data } = await api.post<ExecutionDetail>(
      `/api/v1/workflows/${id}/execute`,
      { initial_items: initialItems },
    );
    return data;
  },
};

export const executions = {
  async list(workflowId?: string): Promise<ExecutionSummary[]> {
    const { data } = await api.get<ExecutionSummary[]>("/api/v1/executions", {
      params: workflowId ? { workflow_id: workflowId } : undefined,
    });
    return data;
  },
  async get(id: string): Promise<ExecutionDetail> {
    const { data } = await api.get<ExecutionDetail>(`/api/v1/executions/${id}`);
    return data;
  },
};

export const nodeTypes = {
  async list(): Promise<NodeType[]> {
    const { data } = await api.get<NodeType[]>("/api/v1/node-types");
    return data;
  },
  async get(slug: string): Promise<NodeType> {
    const { data } = await api.get<NodeType>(`/api/v1/node-types/${slug}`);
    return data;
  },
};

export const credentials = {
  async list(): Promise<CredentialSummary[]> {
    const { data } = await api.get<CredentialSummary[]>("/api/v1/credentials");
    return data;
  },
  async create(body: CredentialCreate): Promise<CredentialSummary> {
    const { data } = await api.post<CredentialSummary>("/api/v1/credentials", body);
    return data;
  },
  async update(id: string, body: CredentialUpdate): Promise<CredentialSummary> {
    const { data } = await api.put<CredentialSummary>(`/api/v1/credentials/${id}`, body);
    return data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/api/v1/credentials/${id}`);
  },
  async test(id: string): Promise<CredentialTestResult> {
    const { data } = await api.post<CredentialTestResult>(`/api/v1/credentials/${id}/test`);
    return data;
  },
};

export const credentialTypes = {
  async list(): Promise<CredentialTypeEntry[]> {
    const { data } = await api.get<CredentialTypeEntry[]>("/api/v1/credential-types");
    return data;
  },
};
