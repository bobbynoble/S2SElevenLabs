<template>
  <div class="connection-status">
    <span class="dot" :class="state"></span>
    <span>{{ label }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: { type: String, required: true },
})

const LABELS = {
  connecting: 'Connecting…',
  waiting_for_patient: 'Waiting for patient to scan QR code…',
  patient_joined: 'Connected',
  processing: 'Translating…',
  speaking: 'Playing translation…',
  ended: 'Session ended',
  session_expired: 'Session expired',
}

const label = computed(() => LABELS[props.state] || props.state)
</script>

<style scoped>
.connection-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-muted);
  font-size: 0.9rem;
}
.dot {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 999px;
  background: var(--color-muted);
  flex-shrink: 0;
}
.dot.patient_joined,
.dot.speaking {
  background: #22c55e;
}
.dot.processing {
  background: #eab308;
}
.dot.ended,
.dot.session_expired {
  background: #ef4444;
}
</style>
