/* eslint-env node */
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: [
    "eslint:recommended",
    "plugin:vue/vue3-recommended",
    "@vue/eslint-config-typescript",
  ],
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  rules: {
    "vue/multi-word-component-names": "off",
    "@typescript-eslint/consistent-type-imports": [
      "warn",
      { prefer: "type-imports" },
    ],
  },
  ignorePatterns: ["dist/", "node_modules/"],
};
