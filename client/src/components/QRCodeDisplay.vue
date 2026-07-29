<template>
  <div class="qr-display">
    <img :src="qrUrl" alt="Scan to join the interpreter session" class="qr-image" />
    <p class="join-url">{{ joinUrl }}</p>
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
.qr-image {
  width: 260px;
  height: 260px;
  background: white;
  padding: 1rem;
  border-radius: 0.75rem;
}
.join-url {
  color: var(--color-muted);
  font-size: 0.85rem;
  word-break: break-all;
  max-width: 320px;
  text-align: center;
}
</style>
