<template>
  <div class="qr-display">
    <p class="instruction">Ask the patient to scan this code with their phone camera</p>
    <img :src="qrUrl" alt="Scan to join the interpreter session" class="qr-image" />
    <p class="join-url">Or share this link: {{ joinUrl }}</p>
  </div>
</template>

<script setup>
defineProps({
  qrUrl: { type: String, required: true },
  joinUrl: { type: String, required: true },
})
</script>

<style scoped>
.qr-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}
.instruction {
  font-size: 1.05rem;
  font-weight: 600;
  text-align: center;
  max-width: 320px;
}
.qr-image {
  width: 260px;
  height: 260px;
  background: white;
  padding: 1rem;
  border-radius: 4px;
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-card);
}
.join-url {
  color: var(--color-muted);
  font-size: 0.85rem;
  word-break: break-all;
  max-width: 320px;
  text-align: center;
}
</style>
