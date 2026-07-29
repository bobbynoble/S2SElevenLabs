<template>
  <div class="caption-panel">
    <p v-if="captions.length === 0" class="empty">The conversation will appear here.</p>
    <div v-for="caption in captions" :key="caption.turn_id" class="caption" :class="caption.speaker">
      <span class="speaker-label">{{ caption.speaker === 'patient' ? 'Patient' : 'Receptionist' }} said ({{ caption.original_lang }})</span>
      <div class="original">{{ caption.original_text }}</div>
      <span class="speaker-label translated-label">Translated ({{ caption.translated_lang }})</span>
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
  gap: 1rem;
  overflow-y: auto;
  padding: 1rem 0;
  flex: 1;
}
.caption {
  padding: 0.85rem 1.1rem;
  border-radius: 4px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 4px solid var(--color-muted);
  box-shadow: var(--shadow-card);
  max-width: 85%;
}
.caption.receptionist {
  align-self: flex-end;
  border-left-color: var(--color-primary);
}
.caption.patient {
  border-left-color: var(--color-accent);
}
.speaker-label {
  display: block;
  color: var(--color-muted);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.translated-label {
  margin-top: 0.6rem;
}
.original {
  color: var(--color-muted);
  font-size: 0.9rem;
}
.translated {
  font-size: 1.15rem;
  font-weight: 600;
  margin-top: 0.1rem;
}
.empty {
  color: var(--color-muted);
  text-align: center;
}
</style>
