<script setup lang="ts">
// API Docs — in-app documentation viewer consuming the OpenAPI schema
// (drf-spectacular). Groups endpoints by tag; per-endpoint method badges,
// paths, summaries + a request tester. Docs look like part of the app
// instead of a separate developer tool.
definePageMeta({ title: 'API Docs', layout: 'default' });

const { api } = useApi();
const { data: schema, pending, error } = await useAsyncData('openapi-schema', () =>
  api.request<any>('/schema/?format=json'),
);

type Op = {
  summary?: string; description?: string; tags?: string[];
  operationId?: string; parameters?: any[]; requestBody?: any; responses?: Record<string, any>;
};
type PathItem = Record<string, Op>;

const grouped = computed(() => {
  const paths: Record<string, PathItem> = schema.value?.paths ?? {};
  const groups = new Map<string, { path: string; method: string; op: Op }[]>();
  for (const [path, item] of Object.entries(paths)) {
    for (const method of ['get', 'post', 'put', 'patch', 'delete']) {
      const op = (item as PathItem)[method];
      if (!op) continue;
      const tag = op.tags?.[0] || 'other';
      if (!groups.has(tag)) groups.set(tag, []);
      groups.get(tag)!.push({ path, method, op });
    }
  }
  return [...groups.entries()].map(([tag, ops]) => ({ tag, ops }));
});

const methodColor: Record<string, string> = {
  get: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400',
  post: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-400',
  put: 'bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400',
  patch: 'bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-400',
  delete: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400',
};

// Request tester state
const selected = ref<{ path: string; method: string; op: Op } | null>(null);
const testBody = ref('{}');
const testResult = ref<{ status: number; body: string } | null>(null);
const testing = ref(false);
const testError = ref('');

const openTester = (entry: { path: string; method: string; op: Op }) => {
  selected.value = entry;
  testResult.value = null;
  testError.value = '';
  testBody.value = entry.method === 'get' ? '{}' : '{}';
};

const closeTester = () => {
  selected.value = null;
  testResult.value = null;
};

const runTest = async () => {
  if (!selected.value) return;
  testing.value = true;
  testError.value = '';
  try {
    const { path, method } = selected.value;
    const isGet = method === 'get';
    const res = await fetch(`${api.base}${path}`, {
      method: method.toUpperCase(),
      headers: { 'Content-Type': 'application/json' },
      body: isGet ? undefined : testBody.value,
    });
    const text = await res.text();
    testResult.value = { status: res.status, body: text };
  } catch (e: any) {
    testError.value = e.message;
  } finally {
    testing.value = false;
  }
};
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-xl font-semibold text-slate-800 dark:text-slate-100">API Documentation</h2>
        <p class="text-sm text-slate-500 dark:text-slate-400">
          Generated from the OpenAPI schema ({{ schema?.info?.title }} v{{ schema?.info?.version }}).
          Full interactive views: <a :href="`${api.base}/schema/swagger-ui/`" target="_blank" class="text-indigo-500 hover:underline">Swagger UI</a>
          · <a :href="`${api.base}/schema/redoc/`" target="_blank" class="text-indigo-500 hover:underline">ReDoc</a>
        </p>
      </div>
    </div>

    <p v-if="error" class="rounded-lg bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">
      Could not load the schema: {{ error.message }}
    </p>

    <!-- Grouped endpoints -->
    <div v-if="!pending && schema" class="space-y-6">
      <div v-for="group in grouped" :key="group.tag" class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div class="border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h3 class="font-semibold text-slate-800 dark:text-slate-100">{{ group.tag }}</h3>
        </div>
        <div class="divide-y divide-slate-100 dark:divide-slate-800">
          <div v-for="entry in group.ops" :key="entry.path + entry.method" class="flex items-center justify-between gap-3 px-5 py-3">
            <div class="flex min-w-0 items-center gap-3">
              <span class="w-16 shrink-0 rounded px-2 py-0.5 text-center text-xs font-bold uppercase" :class="methodColor[entry.method]">
                {{ entry.method }}
              </span>
              <div class="min-w-0">
                <code class="break-all text-sm text-slate-700 dark:text-slate-200">{{ entry.path }}</code>
                <p v-if="entry.op.summary || entry.op.description" class="truncate text-xs text-slate-400">
                  {{ entry.op.summary || entry.op.description }}
                </p>
              </div>
            </div>
            <button class="shrink-0 rounded px-2 py-1 text-xs text-indigo-500 hover:bg-indigo-50 dark:hover:bg-indigo-950" @click="openTester(entry)">
              Test
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Request tester modal -->
    <div v-if="selected" class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/50 p-4" @click.self="closeTester">
      <div class="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl bg-white shadow-2xl dark:bg-slate-900">
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <div class="flex items-center gap-3">
            <span class="rounded px-2 py-0.5 text-xs font-bold uppercase" :class="methodColor[selected.method]">{{ selected.method }}</span>
            <code class="break-all text-sm text-slate-700 dark:text-slate-200">{{ selected.path }}</code>
          </div>
          <button class="text-slate-400 hover:text-slate-600" @click="closeTester">✕</button>
        </div>
        <div class="flex-1 space-y-4 overflow-y-auto p-5">
          <div v-if="selected.op.summary" class="text-sm text-slate-500 dark:text-slate-400">{{ selected.op.summary }}</div>
          <div v-if="selected.method !== 'get'">
            <label class="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Request Body (JSON)</label>
            <textarea v-model="testBody" class="h-32 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs dark:border-slate-700 dark:bg-slate-950" />
          </div>
          <div v-if="testError" class="rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{{ testError }}</div>
          <div v-if="testResult" class="rounded-lg border border-slate-200 dark:border-slate-800">
            <div class="border-b border-slate-200 px-3 py-2 text-xs font-medium dark:border-slate-800" :class="testResult.status < 400 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'">
              {{ testResult.status }}
            </div>
            <pre class="max-h-60 overflow-auto p-3 font-mono text-xs text-slate-700 dark:text-slate-200">{{ testResult.body }}</pre>
          </div>
        </div>
        <div class="flex justify-end gap-3 border-t border-slate-200 px-5 py-3 dark:border-slate-800">
          <button class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800" @click="closeTester">
            Close
          </button>
          <button :disabled="testing" class="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50" @click="runTest">
            {{ testing ? 'Sending…' : 'Send Request' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
