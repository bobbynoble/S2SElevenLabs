<template>
  <button
    type="button"
    class="mic-button"
    :class="{ active }"
    @pointerdown="onPress"
    @pointerup="onRelease"
    @pointerleave="onRelease"
  >
    {{ active ? 'Release to send' : 'Hold to talk' }}
  </button>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['start', 'end'])
const active = ref(false)

function onPress() {
  if (active.value) return
  active.value = true
  emit('start')
}

function onRelease() {
  if (!active.value) return
  active.value = false
  emit('end')
}

defineExpose({ forceRelease: onRelease })
</script>

<style scoped>
.mic-button {
  padding: 1.25rem 2rem;
  border-radius: 999px;
  border: none;
  background: var(--color-accent);
  color: white;
  font-size: 1.1rem;
  font-weight: 600;
  cursor: pointer;
  touch-action: none;
  user-select: none;
}
.mic-button.active {
  background: #ef4444;
}
</style>
