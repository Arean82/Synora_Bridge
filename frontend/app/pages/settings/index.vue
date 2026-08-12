<script setup lang="ts">
// Settings — full System Configuration GUI (views + edits backend/config.ini).
// Faithful port of the Flask settings page: every section is visible and
// editable, core changes (Server/Database) flag a required restart.
definePageMeta({ title: 'Settings', layout: 'default' });

const { api } = useApi();
const { setLayout } = useUiLayout();

type ConfigEntry = { value: any; type: string; options?: string[] };
const config = ref<Record<string, Record<string, ConfigEntry>>>({});
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const savedMsg = ref('');
const restartRequired = ref(false);
const restartScheduled = ref(false);
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

// SECURITY secrets (secret_key / encryption_key): open/close eye reveal toggle.
const revealableKeys = new Set(['secret_key', 'encryption_key']);
const isRevealableKey = (key: string) => revealableKeys.has(key);
const revealedKeys = ref<Record<string, boolean>>({});
const isRevealed = (section: string, key: string) => !!revealedKeys.value[`${section}.${key}`];
const toggleReveal = (section: string, key: string) => {
  const id = `${section}.${key}`;
  revealedKeys.value = { ...revealedKeys.value, [id]: !revealedKeys.value[id] };
};

// UI-level DB mutual exclusion: development is strictly SQLite; production
// uses the [POSTGRES] enabled / [SQLITE] enabled flags (exactly one must be
// on). The inactive database section is disabled and never saved, mirroring
// the backend enforcement in config/settings/base.py.
const environment = computed(() => String(config.value.Server?.environment?.value ?? 'development'));
const isDev = computed(() => environment.value === 'development');
const isProd = computed(() => environment.value === 'production');
const pgEnabled = computed(() => String(config.value.POSTGRES?.enabled?.value ?? 'false') === 'true');
// Effective engine: development is locked to sqlite; production follows the
// enabled flags (POSTGRES enabled → postgresql, else sqlite).
const activeDb = computed<'sqlite' | 'postgresql'>(() =>
  isDev.value ? 'sqlite' : pgEnabled.value ? 'postgresql' : 'sqlite'
);

// Returns the disabled DB section for the active engine ('POSTGRES' when
// SQLite is active, 'SQLITE' when PostgreSQL is active) or ''.
const dbSectionDisabled = (section: string): string =>
  (section === 'POSTGRES' && activeDb.value === 'sqlite') ||
  (section === 'SQLITE' && activeDb.value === 'postgresql')
    ? section : '';

// PostgreSQL connection verification — stateless backend test, never persists.
const pgTesting = ref(false);
const pgTestOk = ref(false);
const pgTestMsg = ref('');
const testPostgres = async () => {
  const pg = config.value.POSTGRES || {};
  pgTesting.value = true;
  pgTestMsg.value = '';
  pgTestOk.value = false;
  try {
    const res = await api.request<any>('/api/v1/config/verify-db/', {
      method: 'POST',
      body: JSON.stringify({
        host: String(pg.host?.value ?? ''),
        port: String(pg.port?.value ?? ''),
        database: String(pg.database?.value ?? ''),
        username: String(pg.username?.value ?? ''),
        password: String(pg.password?.value ?? ''),
      }),
    });
    if (res.ok) {
      pgTestOk.value = true;
      pgTestMsg.value = 'PostgreSQL connection verified.';
    } else {
      pgTestMsg.value = res.error || 'PostgreSQL connection failed.';
    }
  } catch (e: any) {
    pgTestMsg.value = e.message || 'PostgreSQL connection failed.';
  } finally {
    pgTesting.value = false;
  }
};

// CELERY.task_timezone: "use global" checkbox — defaults to Server.timezone.
const useGlobalTz = ref(false);
// Cache.backend: auto-populated (redis) with an optional custom override.
const customCacheBackend = ref(false);

const EDITABLE = new Set([
  'Server.host', 'Server.port', 'Server.environment', 'Server.debug', 'Server.timezone', 'Server.allowed_hosts',
  'POSTGRES.host', 'POSTGRES.port', 'POSTGRES.database', 'POSTGRES.username', 'POSTGRES.password', 'POSTGRES.enabled',
  'SQLITE.path', 'SQLITE.database', 'SQLITE.enabled',
  'CELERY.broker_url', 'CELERY.result_backend', 'CELERY.always_eager', 'CELERY.task_timezone',
  'CELERY.worker_concurrency', 'CELERY.worker_prefetch_multiplier', 'CELERY.task_acks_late',
  'CELERY.task_soft_time_limit', 'CELERY.task_time_limit',
  'SECURITY.secret_key', 'SECURITY.encryption_key',
  'CORS.allowed_origins',
  'UI.theme', 'UI.colormode', 'UI.layout', 'UI.date_format',
  'OPENTELEMETRY.enabled', 'OPENTELEMETRY.otlp_endpoint', 'OPENTELEMETRY.service_name',
  'OPENTELEMETRY.instrument_django', 'OPENTELEMETRY.instrument_requests', 'OPENTELEMETRY.instrument_celery',
  'OPENTELEMETRY.instrument_http',
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
  restartScheduled.value = false;
  restartKeys.value = [];
  try {
    const sections: Record<string, Record<string, string>> = {};
    for (const [sec, keys] of Object.entries(config.value)) {
      sections[sec] = {};
      if (dbSectionDisabled(sec)) continue;
      for (const [key, entry] of Object.entries(keys)) {
        if (!EDITABLE.has(`${sec}.${key}`)) continue;
        // CELERY.task_timezone: when "use global" is checked, send the
        // Server.timezone value (keeps the config consistent).
        if (sec === 'CELERY' && key === 'task_timezone' && useGlobalTz.value) {
          sections[sec][key] = String(config.value.Server?.timezone?.value ?? entry.value);
          continue;
        }
        // Cache.backend: auto-populated (redis) unless custom is checked.
        if (sec === 'Cache' && key === 'backend' && !customCacheBackend.value) {
          sections[sec][key] = 'redis';
          continue;
        }
        sections[sec][key] = String(entry.value);
      }
    }
    // Database-engine mutual exclusion: exactly one database stays enabled
    // (mirrors the backend normalization in config_service.update_config).
    // Enabling one disables the other; disabling one enables the other — the
    // backend re-verifies the PostgreSQL connection before persisting a switch
    // to PostgreSQL and reports db_fallback when it fails.
    if (sections.POSTGRES?.enabled === 'true') {
      sections.SQLITE = { ...(sections.SQLITE || {}), enabled: 'false' };
    }
    if (sections.POSTGRES?.enabled === 'false') {
      sections.SQLITE = { ...(sections.SQLITE || {}), enabled: 'true' };
    }
    if (sections.SQLITE?.enabled === 'true') {
      sections.POSTGRES = { ...(sections.POSTGRES || {}), enabled: 'false' };
    }
    if (sections.SQLITE?.enabled === 'false') {
      sections.POSTGRES = { ...(sections.POSTGRES || {}), enabled: 'true' };
    }
    const res = await api.request<any>('/api/v1/config/', {
      method: 'PUT',
      body: JSON.stringify({ sections }),
    });
    restartRequired.value = res.restart_required;
    restartKeys.value = res.restart_keys || [];
    if (res.restart_scheduled) {
      restartScheduled.value = true;
      const celery = res.celery_restart_required
        ? ' Restart the celery worker separately (Ctrl+C in its terminal, re-run the command).'
        : '';
      savedMsg.value = `Saved. Restarting backend in ~${res.restart_in_seconds ?? 1}s to apply: ${(res.restart_keys || []).join(', ')}.${celery} Reload the page in a few seconds.`;
    } else if (res.restart_blocked) {
      savedMsg.value = `Saved, but the backend did NOT restart: ${res.restart_blocked.error} The server is still running on the previous config — fix the values and save again.`;
    } else if (res.db_fallback) {
      // PostgreSQL switch was not verified — the backend kept SQLite.
      savedMsg.value = `${res.db_fallback.reason} — configuration saved with SQLite.`;
    } else {
      savedMsg.value = `Saved ${(res.updated || []).length} setting(s). Applied without restart.`;
    }
    await load();
    // Apply the UI.layout choice (sidebar/top) instantly — no reload needed.
    const uiLayout = String(config.value.UI?.layout?.value ?? 'sidebar');
    if (uiLayout === 'sidebar' || uiLayout === 'top') setLayout(uiLayout as 'sidebar' | 'top');
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
          Non-core settings apply instantly; core changes (Server/Database) apply automatically — the backend restarts itself on save.
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
    <div v-if="restartRequired && !restartScheduled" class="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
      <strong>Restart needed.</strong> The backend did not restart automatically. Core settings changed: <code>{{ restartKeys.join(', ') }}</code>.
      Fix the values and save again, or restart daphne manually.
    </div>

    <div v-if="loading" class="rounded-xl border p-12 text-center text-slate-400 dark:border-slate-800">Loading configuration…</div>

    <template v-else>
      <div
        v-for="(keys, section) in config"
        :key="section"
        class="rounded-xl border shadow-sm transition-opacity"
        :class="dbSectionDisabled(section)
          ? 'border-slate-200 bg-slate-50 opacity-50 dark:border-slate-800 dark:bg-slate-950'
          : 'border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900'"
      >
        <div class="flex items-center justify-between border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <h3 class="font-semibold text-slate-800 dark:text-slate-100">
            {{ sectionMeta[section]?.label || section }}
          </h3>
          <div class="flex items-center gap-2">
            <span
              v-if="dbSectionDisabled(section)"
              class="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400"
            >
              Disabled — {{ environment }} uses {{ activeDb === 'sqlite' ? 'SQLite' : 'PostgreSQL' }}
            </span>
            <span v-if="sectionMeta[section]?.core" class="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-400">
              Core — auto-restarts on save
            </span>
          </div>
        </div>
        <div class="grid grid-cols-1 gap-4 p-5 md:grid-cols-2" :class="{ 'pointer-events-none': dbSectionDisabled(section) }">
          <div v-for="(entry, key) in keys" :key="key">
            <template v-if="EDITABLE.has(`${section}.${key}`)">
              <label class="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">{{ key }}</label>

              <!-- CELERY.task_timezone: "use global" checkbox (defaults to Server.timezone) -->
              <div v-if="section === 'CELERY' && key === 'task_timezone'" class="space-y-2">
                <label class="flex items-center gap-2 text-sm">
                  <input v-model="useGlobalTz" type="checkbox" class="h-4 w-4 rounded" />
                  Use global timezone (Server)
                </label>
                <select
                  v-model="entry.value"
                  :disabled="useGlobalTz || !!dbSectionDisabled(section)"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950"
                >
                  <option v-for="opt in entry.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
              </div>

              <!-- Cache.backend: auto-populated (redis) with custom override -->
              <div v-else-if="section === 'Cache' && key === 'backend'" class="space-y-2">
                <label class="flex items-center gap-2 text-sm">
                  <input v-model="customCacheBackend" type="checkbox" class="h-4 w-4 rounded" />
                  Custom backend
                </label>
                <input
                  v-model="entry.value"
                  :disabled="!customCacheBackend || !!dbSectionDisabled(section)"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950"
                />
              </div>

              <!-- DB engine flags ([POSTGRES]/[SQLITE] enabled — production selector) -->
              <div v-else-if="(section === 'POSTGRES' || section === 'SQLITE') && key === 'enabled'" class="space-y-1">
                <select
                  v-model="entry.value"
                  :disabled="!!dbSectionDisabled(section)"
                  class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950"
                >
                  <option :value="true">true</option>
                  <option :value="false">false</option>
                </select>
                <p v-if="isDev" class="text-xs text-slate-400">Development is locked to SQLite (this flag only takes effect in production).</p>
                <p v-else-if="section === 'POSTGRES' && activeDb === 'postgresql'" class="text-xs text-slate-400">PostgreSQL is used only after its connection is verified and saved.</p>
              </div>

              <!-- Dropdown from backend-provided options (timezones, units, modes, …) -->
              <select
                v-else-if="entry.options"
                v-model="entry.value"
                :disabled="!!dbSectionDisabled(section)"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              >
                <option v-for="opt in entry.options" :key="opt" :value="opt">{{ opt }}</option>
              </select>

              <select
                v-else-if="entry.type === 'bool'"
                v-model="entry.value"
                :disabled="!!dbSectionDisabled(section)"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              >
                <option :value="true">true</option>
                <option :value="false">false</option>
              </select>

              <input
                v-else-if="entry.type === 'int'"
                v-model="entry.value"
                type="number"
                :disabled="!!dbSectionDisabled(section)"
                class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              />

              <!-- POSTGRES.password: field + "Test connection" (stateless backend verify) -->
              <div v-else-if="section === 'POSTGRES' && key === 'password'" class="space-y-1">
                <div class="flex gap-2">
                  <input
                    v-model="entry.value"
                    type="password"
                    :disabled="!!dbSectionDisabled(section)"
                    class="w-full flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950"
                  />
                  <button
                    @click="testPostgres"
                    :disabled="pgTesting || !!dbSectionDisabled(section)"
                    class="shrink-0 rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                  >
                    {{ pgTesting ? 'Testing…' : 'Test' }}
                  </button>
                </div>
                <p v-if="pgTestMsg" :class="pgTestOk ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'" class="text-xs">
                  {{ pgTestMsg }}
                </p>
              </div>

              <!-- SECURITY.secret_key / encryption_key: eye toggle (reveal/hide) -->
              <div v-else-if="isPasswordKey(section, key) && isRevealableKey(key)" class="flex gap-2">
                <input
                  v-model="entry.value"
                  :type="isRevealed(section, key) ? 'text' : 'password'"
                  :disabled="!!dbSectionDisabled(section)"
                  class="w-full flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-950"
                />
                <button
                  type="button"
                  @click="toggleReveal(section, key)"
                  :disabled="!!dbSectionDisabled(section)"
                  :aria-label="isRevealed(section, key) ? 'Hide value' : 'Show value'"
                  :title="isRevealed(section, key) ? 'Hide' : 'Show'"
                  class="shrink-0 rounded-lg border border-slate-300 px-3 py-2 text-slate-500 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800"
                >
                  <span :class="isRevealed(section, key) ? 'i-heroicons-eye-slash h-4 w-4' : 'i-heroicons-eye h-4 w-4'" />
                </button>
              </div>

              <input
                v-else
                v-model="entry.value"
                :type="isPasswordKey(section, key) ? 'password' : 'text'"
                :disabled="!!dbSectionDisabled(section)"
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
