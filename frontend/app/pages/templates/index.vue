<script setup lang="ts">
// Templates — list + create + clone entry points.
definePageMeta({ title: 'Templates', layout: 'default' });

const { api } = useApi();
const { data: page, pending, refresh } = await useAsyncData('templates', () =>
  api.request<any>('/api/v1/templates/'),
);
const { data: jobs } = await useAsyncData('jobs', () => api.request<any>('/api/v1/jobs/?page_size=200'));

const modeBadge = (mode: string) => ({
  push: ['bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300', 'Push'],
  pull_rest: ['bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300', 'Pull REST'],
  pull_graphql: ['bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300', 'Pull GraphQL'],
}[mode] || ['bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300', mode]);

const jobCount = (templateId: number) =>
  (jobs.value?.results ?? []).filter((j: any) => j.template === templateId).length;

const confirmDelete = async (tpl: any) => {
  if (!window.confirm(`Delete template "${tpl.name}"?`)) return;
  await api.request(`/api/v1/templates/${tpl.id}/`, { method: 'DELETE' });
  await refresh();
};
</script>

<template>
  <div class="space-y-5">
    <div class="flex items-center justify-between">
      <p class="text-sm text-slate-500 dark:text-slate-400">
        {{ page?.count ?? 0 }} bridge templates. Each template defines sources, destinations and field mappings.
      </p>
      <div class="flex gap-2">
        <NuxtLink to="/templates/create" class="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">
          + New Template
        </NuxtLink>
      </div>
    </div>

    <div class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th class="px-5 py-3">Name</th>
              <th class="px-5 py-3">Mode</th>
              <th class="px-5 py-3">Sources</th>
              <th class="px-5 py-3">Destinations</th>
              <th class="px-5 py-3">Jobs</th>
              <th class="px-5 py-3">Updated</th>
              <th class="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
            <tr v-for="tpl in page?.results ?? []" :key="tpl.id">
              <td class="px-5 py-3">
                <NuxtLink :to="`/templates/${tpl.id}`" class="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                  {{ tpl.name }}
                </NuxtLink>
                <p class="text-xs text-slate-400">/api/v1/bridge/pull/{{ tpl.slug }}/</p>
              </td>
              <td class="px-5 py-3">
                <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="modeBadge(tpl.execution_mode)[0]">
                  {{ modeBadge(tpl.execution_mode)[1] }}
                </span>
              </td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ tpl.sources?.length ?? 0 }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ tpl.destinations?.length ?? 0 }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ jobCount(tpl.id) }}</td>
              <td class="px-5 py-3 text-slate-500 dark:text-slate-400">{{ new Date(tpl.updated_at).toLocaleDateString() }}</td>
              <td class="px-5 py-3">
                <div class="flex justify-end gap-2">
                  <NuxtLink :to="`/templates/${tpl.id}`" class="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
                    Edit
                  </NuxtLink>
                  <button class="rounded px-2 py-1 text-xs text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950" @click="confirmDelete(tpl)">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="pending">
              <td colspan="7" class="px-5 py-10 text-center text-slate-400">Loading templates…</td>
            </tr>
            <tr v-if="!pending && !page?.results?.length">
              <td colspan="7" class="px-5 py-10 text-center text-slate-400">
                No templates yet. Run <code>python manage.py seed_demo</code> on the backend.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
