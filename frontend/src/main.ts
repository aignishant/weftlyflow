// Entry point — mounts the Vue app with Pinia + Vue Router.

import "@/styles/tailwind.css";
import "@/styles/global.css";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";

import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "@/App.vue";
import { router } from "@/router";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
