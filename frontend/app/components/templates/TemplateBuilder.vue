<script setup lang="ts">
// TemplateBuilder — two-pane IN/OUT visual builder (original parity).
// Left:  "Source Connection (Input API)"  — source endpoints
// Right: "Destination (Client API)"       — mode of operation, security token,
//        mode-specific config (push destinations / REST endpoints / GQL
//        endpoints) + schedule footer.

const props = defineProps<{ templateId?: number; cloneId?: number }>();
const { api } = useApi();
const router = useRouter();

const form = reactive({
  name: '',
  execution_mode: 'push',
  pull_method: 'GET',
  sources: [] as any[],
  destinations: [] as any[],
  client_credentials: {} as Record<string, any>,
});

const schedule = reactive({ interval: 60, schedule_now: false });
const saving = ref(false);
const error = ref('');
const loading = ref(Boolean(props.templateId || props.cloneId));

const modeOptions = [
  { value: 'push', label: 'Scheduled Push' },
  { value: 'pull_rest', label: 'On-Demand Pull (REST)' },
  { value: 'pull_graphql', label: 'On-Demand Pull (GraphQL)' },
];

const loadId = props.templateId ?? props.cloneId;
if (loadId) {
  const { data } = await useAsyncData(`template-${loadId}`, () =>
    api.request<any>(`/api/v1/templates/${loadId}/`),
  );
  watch(data, (tpl) => {
    if (!tpl) return;
    form.name = props.cloneId ? `${tpl.name} (Clone)` : tpl.name;
    form.execution_mode = tpl.execution_mode;
    form.pull_method = tpl.pull_method;
    form.sources = tpl.sources || [];
    // Clone blanks client-specific details (destinations + credentials).
    form.destinations = props.cloneId ? [] : (tpl.destinations || []);
    form.client_credentials = props.cloneId ? {} : (tpl.client_credentials || {});
    loading.value = false;
  }, { immediate: true });
}

// --- Sources (left pane) ---
const addSource = () => {
  form.sources.push({
    name: `Source ${form.sources.length + 1}`,
    url: '',
    source_type: 'rest',
    method: 'GET',
    auth_token: '',
    selectedApi: '',
    graphql_query: '',
  });
};
const removeSource = (idx: number) => form.sources.splice(idx, 1);
const moveSource = (idx: number, dir: -1 | 1) => {
  const target = idx + dir;
  if (target < 0 || target >= form.sources.length) return;
  const [item] = form.sources.splice(idx, 1);
  form.sources.splice(target, 0, item);
};

// --- Destinations (right pane) ---
const destLabel = computed(() =>
  form.execution_mode === 'push' ? 'Push Destinations' :
  form.execution_mode === 'pull_rest' ? 'REST Pull Endpoints' : 'GraphQL Pull Endpoints',
);

const addDestination = () => {
  form.destinations.push({
    name: `Endpoint ${form.destinations.length + 1}`,
    url: '',
    method: form.execution_mode === 'push' ? 'POST' : 'GET',
    auth_type: 'none',
    credentials: {},
    field_mapping: [] as any[],
  });
};
const removeDestination = (idx: number) => form.destinations.splice(idx, 1);
const moveDestination = (idx: number, dir: -1 | 1) => {
  const target = idx + dir;
  if (target < 0 || target >= form.destinations.length) return;
  const [item] = form.destinations.splice(idx, 1);
  form.destinations.splice(target, 0, item);
};

// --- Field mappings ---
const addMapping = (dest: any) => dest.field_mapping.push({ source: '', target: '' });
const removeMapping = (dest: any, idx: number) => dest.field_mapping.splice(idx, 1);

const allSourceFields = computed(() => {
  const fields: string[] = [];
  form.sources.forEach((_src, i) => {
    fields.push(`source_${i}.id`, `source_${i}.name`);
  });
  return fields;
});

// --- Global security token (right pane) ---
const tokenVisible = ref(false);
const token = computed({
  get: () => form.client_credentials?.token ?? '',
  set: (v: string) => { form.client_credentials = { ...form.client_credentials, token: v }; },
});

const submit = async () => {
  saving.value = true;
  error.value = '';
  try {
    const payload = {
      name: form.name,
      execution_mode: form.execution_mode,
      pull_method: form.pull_method,
      sources: form.sources,
      destinations: form.destinations,
      client_credentials: form.client_credentials,
    };
    let tplId = props.templateId;
    if (tplId) {
      await api.request(`/api/v1/templates/${tplId}/`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      const created = await api.request<any>('/api/v1/templates/', { method: 'POST', body: JSON.stringify(payload) });
      tplId = created.id;
    }
    // Schedule a job when requested (original "schedule immediately").
    if (schedule.schedule_now && tplId) {
      await api.request('/api/v1/jobs/', {
        method: 'POST',
        body: JSON.stringify({ template: tplId, schedule_interval: Math.max(1, schedule.interval) }),
      });
    }
    await router.push('/templates');
  } catch (e: any) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <div class="space-y-5">
    <div v-if="loading" class="rounded-xl border p-12 text-center text-slate-400 dark:border-slate-800">Loading…</div>

    <template v-else>
      <div v-if="error" class="rounded-lg bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">{{ error }}</div>

      <!-- Template name -->
      <div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <label class="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Template Name *</label>
        <input v-model="form.name" type="text" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
      </div>

      <!-- Two-pane IN/OUT -->
      <div class="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <!-- LEFT: Source Connection (Input API) -->
        <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <h3 class="font-bold text-slate-800 dark:text-slate-100">Source Connection (Input API)</h3>
            <button class="theme-btn rounded-lg bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-500" @click="addSource">
              + Add Endpoint
            </button>
          </div>
          <div class="max-h-[70vh] space-y-4 overflow-y-auto p-4">
            <div v-if="!form.sources.length" class="rounded-lg bg-slate-50 p-4 text-center text-sm text-slate-400 dark:bg-slate-950">
              No source endpoints yet.
            </div>
            <div v-for="(src, i) in form.sources" :key="i" class="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
              <div class="mb-2 flex items-center justify-between">
                <span class="text-sm font-medium text-slate-600 dark:text-slate-300">Source {{ i + 1 }}</span>
                <div class="flex items-center gap-1">
                  <button class="text-xs text-slate-400 hover:text-slate-600" :disabled="i === 0" @click="moveSource(i, -1)">↑</button>
                  <button class="text-xs text-slate-400 hover:text-slate-600" :disabled="i === form.sources.length - 1" @click="moveSource(i, 1)">↓</button>
                  <button class="text-xs text-rose-500 hover:underline" @click="removeSource(i)">Remove</button>
                </div>
              </div>
              <div class="space-y-2">
                <input v-model="src.name" placeholder="Name" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
                <input v-model="src.url" placeholder="https://api.example.com/…" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
                <div class="grid grid-cols-2 gap-2">
                  <select v-model="src.source_type" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950">
                    <option value="rest">REST</option>
                    <option value="graphql">GraphQL</option>
                  </select>
                  <input v-model="src.method" placeholder="Method" class="rounded-lg border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
                </div>
                <input v-model="src.auth_token" placeholder="Auth token (optional)" type="password" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
                <textarea v-if="src.source_type === 'graphql'" v-model="src.graphql_query" placeholder="GraphQL query…" class="w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
              </div>
            </div>
          </div>
        </div>

        <!-- RIGHT: Destination (Client API) -->
        <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 lg:col-span-2">
          <div class="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <h3 class="font-bold text-slate-800 dark:text-slate-100">Destination (Client API)</h3>
          </div>

          <div class="grid grid-cols-1 gap-4 p-4 md:grid-cols-2">
            <!-- Mode of Operation -->
            <div>
              <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">Mode of Operation</label>
              <select v-model="form.execution_mode" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
                <option v-for="o in modeOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <!-- Global Security Token -->
            <div>
              <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">Global Security Token (Bearer)</label>
              <div class="relative">
                <input v-model="token" :type="tokenVisible ? 'text' : 'password'" placeholder="Leave empty for no auth"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 pr-10 text-sm dark:border-slate-700 dark:bg-slate-950" />
                <button type="button" class="absolute inset-y-0 right-0 flex items-center pr-3 text-slate-400 hover:text-slate-600" @click="tokenVisible = !tokenVisible">
                  {{ tokenVisible ? 'hide' : 'show' }}
                </button>
              </div>
            </div>
            <!-- Pull method (REST mode) -->
            <div v-if="form.execution_mode !== 'push'">
              <label class="mb-1 block text-sm font-medium text-slate-600 dark:text-slate-300">Pull Method</label>
              <select v-model="form.pull_method" class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
                <option>GET</option><option>POST</option>
              </select>
            </div>
          </div>

          <!-- Mode-specific config blocks -->
          <div class="border-t border-slate-200 p-4 dark:border-slate-800">
            <div class="mb-3 flex items-center justify-between">
              <h4 class="text-sm font-bold text-slate-700 dark:text-slate-300">{{ destLabel }}</h4>
              <button class="theme-btn rounded-lg bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-500" @click="addDestination">
                + Add {{ form.execution_mode === 'push' ? 'Destination' : 'Endpoint' }}
              </button>
            </div>

            <div v-if="!form.destinations.length" class="rounded-lg bg-slate-50 p-4 text-center text-sm text-slate-400 dark:bg-slate-950">
              No {{ form.execution_mode === 'push' ? 'destinations' : 'endpoints' }} yet.
            </div>

            <div v-for="(dest, di) in form.destinations" :key="di" class="mb-4 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
              <div class="mb-3 flex items-center justify-between">
                <span class="text-sm font-medium text-slate-600 dark:text-slate-300">{{ form.execution_mode === 'push' ? 'Destination' : 'Endpoint' }} {{ di + 1 }}</span>
                <div class="flex items-center gap-2">
                  <button class="text-xs text-slate-400 hover:text-slate-600" :disabled="di === 0" @click="moveDestination(di, -1)">↑</button>
                  <button class="text-xs text-slate-400 hover:text-slate-600" :disabled="di === form.destinations.length - 1" @click="moveDestination(di, 1)">↓</button>
                  <button class="text-xs text-rose-500 hover:underline" @click="removeDestination(di)">Remove</button>
                </div>
              </div>

              <div class="mb-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                <input v-model="dest.name" placeholder="Name" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
                <input v-if="form.execution_mode === 'push'" v-model="dest.url" placeholder="https://dest.example.com/ingest" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950" />
                <select v-model="dest.method" class="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950">
                  <option v-for="m in (form.execution_mode === 'push' ? ['POST','PUT','PATCH'] : ['GET','POST'])" :key="m">{{ m }}</option>
                </select>
              </div>

              <!-- Field mappings -->
              <div class="rounded-lg bg-slate-50 p-3 dark:bg-slate-950">
                <div class="mb-2 flex items-center justify-between">
                  <span class="text-xs font-medium uppercase tracking-wide text-slate-500">Field Mapping</span>
                  <button class="text-xs text-indigo-500 hover:underline" @click="addMapping(dest)">+ Add Mapping</button>
                </div>
                <div v-for="(m, mi) in dest.field_mapping" :key="mi" class="mb-2 flex items-center gap-2">
                  <select v-model="m.source" class="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950">
                    <option value="">source field…</option>
                    <option v-for="f in allSourceFields" :key="f" :value="f">{{ f }}</option>
                  </select>
                  <span class="text-slate-400">→</span>
                  <input v-model="m.target" placeholder="target.path[0].field" class="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950" />
                  <button class="text-xs text-rose-500 hover:underline" @click="removeMapping(dest, mi)">✕</button>
                </div>
              </div>
            </div>
          </div>

          <!-- Footer: schedule settings (original parity) -->
          <div class="flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950">
            <label class="flex items-center gap-2 text-sm">
              <input v-model="schedule.schedule_now" type="checkbox" class="h-4 w-4 rounded" />
              Run Every (Seconds):
              <input v-model.number="schedule.interval" type="number" min="1" class="w-24 rounded-lg border border-slate-300 px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-950" />
            </label>
            <div class="flex gap-3">
              <NuxtLink to="/templates" class="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800">
                Cancel
              </NuxtLink>
              <button
                :disabled="saving || !form.name"
                class="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                @click="submit"
              >
                {{ saving ? 'Saving…' : (props.templateId ? 'Save Changes' : 'Create Template') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
