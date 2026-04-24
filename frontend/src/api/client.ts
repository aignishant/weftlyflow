// Axios-based API client. One instance per page load; the bearer token is
// pulled from the auth store on every request so refreshes survive reloads.

import axios, {
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from "axios";

const TOKEN_STORAGE_KEY = "weftlyflow.access_token";
const PROJECT_STORAGE_KEY = "weftlyflow.project_id";

function makeClient(): AxiosInstance {
  const client = axios.create({
    baseURL: "",
    timeout: 30_000,
    headers: { "Content-Type": "application/json" },
  });

  client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    const project = window.localStorage.getItem(PROJECT_STORAGE_KEY);
    if (project) {
      config.headers["X-Weftlyflow-Project"] = project;
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    (error: unknown) => {
      // A 401 on any authenticated request means the stored token is stale
      // (expired, revoked, or from a wiped DB). Clear it and bounce to /login
      // instead of letting every store explode silently. Skip when we're
      // already on /login or the failing call *is* the login endpoint itself,
      // to avoid a redirect loop.
      if (axios.isAxiosError(error) && error.response?.status === 401) {
        const url = error.config?.url ?? "";
        const onLoginPage = window.location.pathname.startsWith("/login");
        const isAuthCall = url.includes("/api/v1/auth/login");
        if (!onLoginPage && !isAuthCall) {
          window.localStorage.removeItem(TOKEN_STORAGE_KEY);
          window.localStorage.removeItem(PROJECT_STORAGE_KEY);
          const redirect = encodeURIComponent(
            window.location.pathname + window.location.search,
          );
          window.location.replace(`/login?redirect=${redirect}`);
        }
      }
      return Promise.reject(error);
    },
  );

  return client;
}

export const api = makeClient();

export function setStoredToken(token: string | null): void {
  if (token === null) {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } else {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  }
}

export function getStoredToken(): string | null {
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredProject(projectId: string | null | undefined): void {
  if (!projectId) {
    window.localStorage.removeItem(PROJECT_STORAGE_KEY);
  } else {
    window.localStorage.setItem(PROJECT_STORAGE_KEY, projectId);
  }
}

export function getStoredProject(): string | null {
  return window.localStorage.getItem(PROJECT_STORAGE_KEY);
}

export function extractErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as
      | { error?: { message?: string; code?: string }; detail?: unknown }
      | undefined;
    if (data?.error?.message) {
      return data.error.message;
    }
    if (typeof data?.detail === "string") {
      return data.detail;
    }
    if (err.message) {
      return err.message;
    }
  }
  if (err instanceof Error) {
    return err.message;
  }
  return String(err);
}

export type { AxiosRequestConfig };
