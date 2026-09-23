<template>
  <div class="connection-status" :class="state" role="status">
    <span class="dot" aria-hidden="true"></span>
    <span>{{ label }}</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  state: { type: String, required: true },
  detail: { type: String, default: null },
})

const LABELS = {
  connecting: 'Connecting…',
  waiting_for_patient: 'Waiting for patient to scan QR code…',
  patient_joined: 'Connected',
  processing: 'Translating…',
  speaking: 'Playing translation…',
  ended: 'Session ended',
  coding: 'Determining clinical code…',
  session_expired: 'Session expired',
  error: 'Something went wrong',
}

const label = computed(() => {
  if (props.state === 'error') return props.detail || LABELS.error
  return LABELS[props.state] || props.state
})
</script>

<style scoped>
.connection-status {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-text);
  font-size: 0.95rem;
  font-weight: 700;
  background: #e8edee;
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0.4rem 0.9rem 0.4rem 0.6rem;
}
.dot {
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 999px;
  background: var(--color-muted);
  flex-shrink: 0;
}
.connection-status.patient_joined,
.connection-status.speaking {
  background: #e5f5ea;
  border-color: #b6e3c4;
}
.connection-status.patient_joined .dot,
.connection-status.speaking .dot {
  background: var(--color-accent);
}
.connection-status.processing .dot,
.connection-status.speaking .dot,
.connection-status.coding .dot {
  animation: status-pulse 1.2s ease-in-out infinite;
}
.connection-status.processing .dot,
.connection-status.coding .dot {
  background: #ffb81c;
}
@keyframes status-pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.35;
  }
}
@media (prefers-reduced-motion: reduce) {
  .connection-status.processing .dot,
  .connection-status.speaking .dot,
  .connection-status.coding .dot {
    animation: none;
  }
}
.connection-status.ended,
.connection-status.session_expired,
.connection-status.error {
  background: var(--color-error-bg);
  border-color: #f4c6c1;
  color: var(--color-error);
}
.connection-status.ended .dot,
.connection-status.session_expired .dot,
.connection-status.error .dot {
  background: var(--color-error);
}
</style>
