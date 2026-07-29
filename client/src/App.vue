<template>
  <router-view />
</template>

<style>
:root {
  --color-bg: #0f172a;
  --color-surface: #1e293b;
  --color-border: #334155;
  --color-text: #e2e8f0;
  --color-muted: #64748b;
  --color-accent: #3b82f6;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--color-bg);
  color: var(--color-text);
}

button {
  font-family: inherit;
}
</style>
