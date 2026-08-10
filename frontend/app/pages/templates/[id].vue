<script setup lang="ts">
// Edit template page (also the detail view with generated endpoint links).
definePageMeta({ title: 'Edit Template', layout: 'default' });

const route = useRoute();
const id = Number(route.params.id);
</script>

<template>
  <div class="space-y-4">
    <TemplateBuilder :template-id="id" />
  </div>
</template>
