<template>
  <button
    type="button"
    class="mic-button"
    :class="{ active }"
    :aria-pressed="active"
    @pointerdown="onPress"
    @pointerup="onRelease"
    @pointerleave="onRelease"
  >
    <span class="icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
        <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" />
        <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.93V20H9a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2h-2v-2.07A7 7 0 0 0 19 11z" />
      </svg>
    </span>
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
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 1.25rem 2rem;
  border-radius: 999px;
  border: none;
  background: var(--color-accent);
  color: white;
  font-size: 1.15rem;
  font-weight: 700;
  cursor: pointer;
  touch-action: none;
  user-select: none;
  box-shadow: 0 4px 0 var(--color-accent-dark);
}
.mic-button .icon {
  display: inline-flex;
}
.mic-button.active {
  background: var(--color-error);
  box-shadow: 0 4px 0 #8f1c12;
  transform: translateY(2px);
}
</style>
