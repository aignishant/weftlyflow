// Verifies the NodeTypes store's lookup helper behaves correctly across
// empty + populated states. No network — we seed the ref directly.

import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import { useNodeTypesStore } from "@/stores/nodeTypes";
import type { NodeType } from "@/types/api";

const sampleType: NodeType = {
  type: "weftlyflow.http_request",
  version: 1,
  display_name: "HTTP Request",
  description: "",
  icon: "",
  category: "core",
  group: [],
  inputs: [{ name: "main", kind: "main", index: 0 }],
  outputs: [{ name: "main", kind: "main", index: 0 }],
  credentials: [],
  properties: [],
};

describe("useNodeTypesStore", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("empty lookup returns undefined", () => {
    const store = useNodeTypesStore();
    expect(store.lookup("weftlyflow.http_request")).toBeUndefined();
  });

  it("lookup finds a seeded type and bySlug reflects it", () => {
    const store = useNodeTypesStore();
    store.items = [sampleType];
    store.loaded = true;
    // Pinia proxies reactive refs, so we compare by shape rather than identity.
    expect(store.lookup("weftlyflow.http_request")).toEqual(sampleType);
    expect(store.bySlug.get("weftlyflow.http_request")).toEqual(sampleType);
  });
});
