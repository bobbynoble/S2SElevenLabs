<template>
  <header class="app-header">
    <div class="bar">
      <span class="badge" aria-hidden="true">NHS</span>
      <span class="service-name">Hospital Reception Interpreter</span>
    </div>
  </header>
</template>

<script setup>
</script>

<style scoped>
.app-header {
  background: var(--color-primary);
  padding: 0.75rem 1.25rem;
}
.bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  max-width: 640px;
  margin: 0 auto;
}
.badge {
  background: #ffffff;
  color: var(--color-primary);
  font-weight: 800;
  font-size: 1rem;
  letter-spacing: 0.03em;
  padding: 0.25rem 0.5rem;
  border-radius: 3px;
  line-height: 1;
}
.service-name {
  color: #ffffff;
  font-size: 1.05rem;
  font-weight: 700;
}
</style>
