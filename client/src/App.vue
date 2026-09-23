<template>
  <router-view />
</template>

<style>
:root {
  /* NHS Digital service manual palette (nhsuk-frontend design tokens) */
  --color-bg: #f0f4f5;
  --color-surface: #ffffff;
  --color-border: #d8dde0;
  --color-text: #212b32;
  --color-muted: #4c6272;
  --color-primary: #005eb8;
  --color-primary-dark: #003087;
  --color-accent: #007f3b;
  --color-accent-dark: #00401f;
  --color-error: #d5281b;
  --color-error-bg: #fdf2f2;
  --color-focus: #ffeb3b;
  --shadow-card: 0 1px 3px rgba(33, 43, 50, 0.12);
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
  font-family: Arial, 'Helvetica Neue', Helvetica, sans-serif;
  background: var(--color-bg);
  color: var(--color-text);
  -webkit-font-smoothing: antialiased;
}

button {
  font-family: inherit;
}

/* NHS-style visible focus state: a solid yellow highlight, never suppressed */
a:focus-visible,
button:focus-visible,
[tabindex]:focus-visible {
  outline: 3px solid var(--color-focus);
  outline-offset: 0;
  box-shadow: 0 0 0 4px var(--color-text);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 1rem 1.5rem;
  border-radius: 4px;
  border: 2px solid transparent;
  font-size: 1.1rem;
  font-weight: 700;
  cursor: pointer;
  min-height: 48px;
  min-width: 48px;
  transition: background-color 0.1s ease;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.btn-primary {
  background: var(--color-accent);
  color: #ffffff;
  box-shadow: 0 4px 0 var(--color-accent-dark);
}
.btn-primary:hover:not(:disabled) {
  background: #006428;
}
.btn-primary:active:not(:disabled) {
  box-shadow: none;
  transform: translateY(4px);
}
.btn-secondary {
  background: #ffffff;
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.btn-secondary:hover:not(:disabled) {
  background: #f0f4f5;
}
</style>
