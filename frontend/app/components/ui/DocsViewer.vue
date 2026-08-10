<script setup lang="ts">
// DocsViewer — markdown documentation modal (original docs_modal.html parity).
// Buttons for README + docs/*.md; renders markdown client-side with marked.
import { marked } from 'marked';

const { api } = useApi();

const open = ref(false);
const loading = ref(false);
const error = ref('');
const title = ref('Documentation');
const html = ref('');

const DOCS = [
  { file: 'README.md', label: 'README' },
  { file: 'ARCHITECTURE.md', label: 'Architecture' },
  { file: 'DEPLOYMENT.md', label: 'Deployment' },
  { file: 'SECURITY.md', label: 'Security' },
];

const loadDoc = async (file: string, label: string) => {
  loading.value = true;
  error.value = '';
  title.value = label;
  try {
    const res = await api.request<any>(`/api/v1/docs/markdown/${encodeURIComponent(file)}/`);
    html.value = marked.parse(res.content) as string;
  } catch (e: any) {
    error.value = e.message;
    html.value = '';
  } finally {
    loading.value = false;
  }
};

const show = async () => {
  open.value = true;
  await loadDoc('README.md', 'README');
};
const hide = () => { open.value = false; };
defineExpose({ show });
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 p-4" @click.self="hide">
    <div class="flex h-[80vh] w-full max-w-3xl flex-col rounded-xl bg-white shadow-2xl dark:bg-slate-900">
      <div class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
        <h3 class="text-lg font-bold text-slate-800 dark:text-slate-100">{{ title }}</h3>
        <button class="text-slate-400 hover:text-slate-600" @click="hide">✕</button>
      </div>

      <!-- Doc selector buttons -->
      <div class="flex flex-wrap gap-2 border-b border-slate-200 px-5 py-3 dark:border-slate-800">
        <button
          v-for="d in DOCS"
          :key="d.file"
          class="rounded-lg px-3 py-1 text-xs font-medium"
          :class="title === d.label
            ? 'bg-indigo-600 text-white'
            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'"
          @click="loadDoc(d.file, d.label)"
        >{{ d.label }}</button>
      </div>

      <!-- Rendered markdown -->
      <div class="flex-1 overflow-y-auto p-5">
        <div v-if="error" class="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{{ error }}</div>
        <div v-else-if="loading" class="text-center text-slate-400">Loading…</div>
        <div v-else class="prose-sm max-w-none" v-html="html" />
      </div>
    </div>
  </div>
</template>
