<script setup lang="ts">
// Settings — full System Configuration GUI (views + edits backend/config.ini).
// Faithful port of the Flask settings page: every section is visible and
// editable, core changes (Server/Database) flag a required restart.
definePageMeta({ title: 'Settings', layout: 'default' });

const { api } = useApi();

const config = ref<Record<string, Record<string, { value: any; type: string }>>>({});
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const savedMsg = ref('');
const restartRequired = ref(false);
const restartKeys = ref<string[]>([]);

// Section display metadata (label + core badge).
const sectionMeta: Record<string, { label: string; core?: boolean }> = {
  Server: { label: 'Server Settings', core: true },
  POSTGRES: { label: 'PostgreSQL Configuration', core: true },
  SQLITE: { label: 'SQLite Configuration', core: true },
  CELERY: { label: 'Celery (Workers & Scheduler)', core: true },
  SECURITY: { label: 'Security (Secrets)', core: true },
  CORS: { label: 'CORS (Frontend Origins)' },
  UI: { label: 'Interface' },
  OPENTELEMETRY: { label: 'OpenTelemetry' },
  RateLimit: { label: 'Rate Limiting' },
  Cache: { label: 'Pull Response Cache' },
  DatabasePool: { label: 'Database Pooling' },
  ReverseProxy: { label: 'Reverse Proxy' },
  Logging: { label: 'Logging' },
  RetryQueue: { label: 'Retry Queue' },
  Swagger: { label: 'Swagger / Spec Refresh' },
  Email: { label: 'Email Alerts' },
};

const isPasswordKey = (section: string, key: string) =>
  ['password', 'secret_key', 'encryption_key'].includes(key);

// Which keys are editable vs informational.
const EDITABLE = new Set([
  'Server.host', 'Server.port', 'Server.environment', 'Server.debug', 'Server.timezone', 'Server.allowed_hosts',
  'POSTGRES.host', 'POSTGRES.port', 'POSTGRES.database', 'POSTGRES.username', 'POSTGRES.password',
  'SQLITE.path', 'SQLITE.database',
  'CELERY.broker_url', 'CELERY.result_backend', 'CELERY.always_eager', 'CELERY.task_timezone',
  'CELERY.worker_concurrency', 'CELERY.worker_prefetch_multiplier', 'CELERY.task_acks_late',
  'CELERY.task_soft_time_limit', 'CELERY.task_time_limit',
  'SECURITY.secret_key', 'SECURITY.encryption_key',
  'CORS.allowed_origins',
  'UI.theme', 'UI.colormode', 'UI.layout', 'UI.date_format',
  'OPENTELEMETRY.enabled', 'OPENTELEMETRY.otlp_endpoint', 'OPENTELEMETRY.service_name',
  'OPENTELEMETRY.instrument_django', 'OPENTELEMETRY.instrument_requests', 'OPENTELEMETRY.instrument_celery',
  'OPENTELEMETRY.instrument_db', 'OPENTELEMETRY.instrument_http',
  'RateLimit.enabled', 'RateLimit.rate', 'RateLimit.period',
  'Cache.enabled', 'Cache.backend', 'Cache.default_ttl_seconds',
  'DatabasePool.enabled', 'DatabasePool.max_age_seconds',
  'ReverseProxy.enabled',
  'Logging.log_dir', 'Logging.rotation', 'Logging.backup_count',
  'RetryQueue.retention_minutes',
  'Swagger.refresh_interval', 'Swagger.refresh_unit',
  'Email.mode', 'Email.sender_email', 'Email.recipient_emails', 'Email.smtp_host', 'Email.smtp_port',
  'Email.smtp_user', 'Email.smtp_password', 'Email.throttle_enabled', 'Email.throttle_minutes',
]);

const load = async () => {
  loading.value = true;
  try {
    const res = await api.request<any>('/api/v1/config/');
    config.value = res.sections;
  } catch (e: any) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
};

const save = async () => {
  saving.value = true;
  error.value = '';
  savedMsg.value = '';
  restartRequired.value = false;
  restartKeys.value = [];
  try {
    const sections: Record<string, Record<string, string>> = {};
    for (const [sec, keys] of Object.entries(config.value)) {
      sections[sec] = {};
      for (const [key, entry] of Object.entries(keys)) {
        if (!EDITABLE.has(`${sec}.${key}`)) continue;
        sections[sec][key] = String(entry.value);
      }
    }
    const res = await api.request<any>('/api/v1/config/', {
      method: 'PUT',
      body: JSON.stringify({ sections }),
    });
    restartRequired.value = res.restart_required;
    restartKeys.value = res.restart_keys || [];
    savedMsg.value = `Saved ${(res.updated || []).length} setting(s).`;
    await load();
  } catch (e: any) {
    error.value = e.message;
  } finally {
    saving.value = false;
  }
};

await load();
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-5">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-semibold text-slate-800 dark:text-slate-100">System Configuration</h2>
        <p class="text-sm text-slate-500 dark:text-slate-400">
          View and edit the runtime configuration (<code>backend/config.ini</code>).
          Core changes (Server/Database) require an app restart.
        </p>
      </div>
      <button
        :disabled="saving || loading"
        class="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        @click="save"
      >
        {{ saving ? 'Saving…' : 'Save Configuration' }}
      </button>
    </div>

    <div v-if="error" class="rounded-lg bg-rose-50 p-4 text-sm text-rose-700 dark:bg-rose-950 dark:text-rose-300">
      {{ error }}
    </div>
    <div v-if="savedMsg" class="rounded-lg bg-emerald-50 p-4 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
      {{ savedMsg }}
    </div>
    <div v-if="restartRequired" class="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
      <strong>Restart required.</strong> Core settings changed: <code>{{ restartKeys.join(', ') }}</code>.
      Restart the backend (daphne + celery) for these to take effect.
    </div>

    <div v-if="loading" class="rounded-xl border p-12 text-center text-slate-400 dark:border-slate-800">Loading configuration…</div>

    <template v-else>
      <div
        v-for="(keys, section) in config"
        :key="section"
        class="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h3 class="font-semibold text-slate-800 dark:text-slate-100">
            {{ sectionMeta[section]?.label || section }}
          </h3>
          <span v-if="sectionMeta[section]?.core" class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-400">
            Core — restart on change
          </span>
        </div>
        <div class="grid grid-cols-1 gap-4 p-5 md:grid-cols-2">
          <div v-for="(entry, key) in keys" :key="key">
            <template v-if="EDITABLE.has(`${section}.${key}`)">
              <label class="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">{{ key }}</label>
              <select
                v-if="entry.type === 'bool'"
                v-model="entry.value"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              >
                <option :value="true">true</option>
                <option :value="false">false</option>
              </select>
              <input
                v-else-if="entry.type === 'int'"
                v-model="entry.value"
                type="number"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              />
              <input
                v-else
                v-model="entry.value"
                :type="isPasswordKey(section, key) ? 'password' : 'text'"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              />
            </template>
            <div v-else class="text-sm text-slate-400">
              <div class="mb-1 text-xs">{{ key }}</div>
              <code class="break-all">{{ entry.value }}</code>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
