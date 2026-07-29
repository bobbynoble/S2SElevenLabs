<template>
  <div class="language-picker">
    <button
      v-for="lang in languages"
      :key="lang.code"
      type="button"
      class="language-option"
      :class="{ active: lang.code === modelValue }"
      @click="$emit('update:modelValue', lang.code)"
    >
      <span class="native">{{ lang.native_name }}</span>
      <span class="english">{{ lang.english_name }}</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  languages: { type: Array, required: true },
  modelValue: { type: String, default: null },
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.language-picker {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.75rem;
}
.language-option {
  padding: 1rem;
  border-radius: 0.75rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  text-align: left;
}
.language-option.active {
  border-color: var(--color-accent);
  background: #1d3a63;
}
.native {
  font-size: 1.1rem;
  font-weight: 600;
}
.english {
  font-size: 0.85rem;
  color: var(--color-muted);
}
</style>
