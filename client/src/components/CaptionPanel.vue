<template>
  <div class="caption-panel">
    <p v-if="captions.length === 0" class="empty">The conversation will appear here.</p>
    <div v-for="caption in captions" :key="caption.turn_id" class="caption" :class="caption.speaker">
      <div class="original">{{ caption.original_text }}</div>
      <div class="translated">{{ caption.translated_text }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  captions: { type: Array, required: true },
})
</script>

<style scoped>
.caption-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  padding: 1rem 0;
  flex: 1;
}
.caption {
  padding: 0.75rem 1rem;
  border-radius: 0.75rem;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  max-width: 80%;
}
.caption.receptionist {
  align-self: flex-end;
  background: #1d3a63;
}
.original {
  color: var(--color-muted);
  font-size: 0.85rem;
}
.translated {
  font-size: 1.05rem;
  margin-top: 0.25rem;
}
.empty {
  color: var(--color-muted);
  text-align: center;
}
</style>
