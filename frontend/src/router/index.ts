// Vue Router wiring + auth guard. Every route except /login requires a
// bearer token; the guard redirects to /login otherwise and back to the
// original destination on success.

import {
  createRouter,
  createWebHistory,
  type RouteRecordRaw,
} from "vue-router";

import { useAuthStore } from "@/stores/auth";

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/Login.vue"),
    meta: { public: true },
  },
  {
    path: "/",
    name: "home",
    component: () => import("@/views/Home.vue"),
  },
  {
    path: "/workflows/:id",
    name: "editor",
    component: () => import("@/views/Editor.vue"),
    props: true,
  },
  {
    path: "/executions",
    name: "executions",
    component: () => import("@/views/Executions.vue"),
  },
  {
    path: "/executions/:id",
    name: "execution-detail",
    component: () => import("@/views/ExecutionDetail.vue"),
    props: true,
  },
  {
    path: "/credentials",
    name: "credentials",
    component: () => import("@/views/Credentials.vue"),
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/",
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const auth = useAuthStore();
  if (!auth.token) {
    auth.hydrate();
  }
  if (to.meta.public) {
    return true;
  }
  if (!auth.isAuthenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  return true;
});
