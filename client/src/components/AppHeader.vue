<template>
  <header class="app-header">
    <div class="bar">
      <span class="service-name">DXC Demo for NHS Participants</span>
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
.service-name {
  color: #ffffff;
  font-size: 1.05rem;
  font-weight: 700;
}
</style>
