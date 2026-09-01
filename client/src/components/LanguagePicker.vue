<template>
  <div class="language-picker" role="group" aria-label="Choose your language">
    <button
      v-for="lang in languages"
      :key="lang.code"
      type="button"
      class="language-option"
      :class="{ active: lang.code === modelValue }"
      :aria-pressed="lang.code === modelValue"
      @click="$emit('update:modelValue', lang.code)"
    >
      <span class="check" aria-hidden="true">✓</span>
      <span class="labels">
        <span class="native">{{ lang.native_name }}</span>
        <span class="english">{{ lang.english_name }}</span>
      </span>
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
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 0.75rem;
}
.language-option {
  position: relative;
  padding: 1rem 1rem 1rem 2.5rem;
  min-height: 64px;
  border-radius: 4px;
  border: 2px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  text-align: left;
  box-shadow: var(--shadow-card);
}
.language-option:hover {
  border-color: var(--color-primary);
}
.language-option.active {
  border-color: var(--color-primary);
  background: #e8edee;
}
.check {
  position: absolute;
  left: 0.85rem;
  color: var(--color-primary);
  font-weight: 700;
  font-size: 1.1rem;
  visibility: hidden;
}
.language-option.active .check {
  visibility: visible;
}
.labels {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.native {
  font-size: 1.1rem;
  font-weight: 700;
}
.english {
  font-size: 0.85rem;
  color: var(--color-muted);
}
</style>
