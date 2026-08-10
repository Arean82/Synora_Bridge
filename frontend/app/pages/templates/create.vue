<script setup lang="ts">
// New template page. Supports ?clone=<id> to pre-fill from an existing
// template with client-specific details (destinations) blanked — original parity.
definePageMeta({ title: 'New Template', layout: 'default' });

const route = useRoute();
const cloneId = route.query.clone ? Number(route.query.clone) : undefined;
</script>

<template>
  <TemplatesTemplateBuilder :clone-id="cloneId" />
</template>
