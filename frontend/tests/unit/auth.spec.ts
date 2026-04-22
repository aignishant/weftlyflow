// Smoke tests for the auth store — just enough to prove the store module
// wires up and persists via the same localStorage helpers the router guard
// reads.

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "@/stores/auth";

describe("useAuthStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    window.localStorage.clear();
  });

  it("starts unauthenticated", () => {
    const auth = useAuthStore();
    expect(auth.isAuthenticated).toBe(false);
  });

  it("hydrates from localStorage", () => {
    window.localStorage.setItem("weftlyflow.access_token", "abc");
    window.localStorage.setItem("weftlyflow.project_id", "pr_1");
    const auth = useAuthStore();
    auth.hydrate();
    expect(auth.isAuthenticated).toBe(true);
    expect(auth.token).toBe("abc");
    expect(auth.projectId).toBe("pr_1");
  });

  it("clear wipes localStorage + identity", () => {
    const auth = useAuthStore();
    auth.token = "t";
    auth.email = "x@y";
    auth.projectId = "pr_1";
    window.localStorage.setItem("weftlyflow.access_token", "t");
    auth.clear();
    expect(auth.isAuthenticated).toBe(false);
    expect(window.localStorage.getItem("weftlyflow.access_token")).toBeNull();
  });
});
