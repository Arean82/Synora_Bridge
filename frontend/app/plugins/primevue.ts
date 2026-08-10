// PrimeVue registration (fallback UI kit — Nuxt components preferred).
//
// PrimeVue v3 (MIT, free) as specified: Nuxt 4 native components first,
// PrimeVue v3 second. Uses the v3 CSS theme import (no @primeuix/themes,
// which is v4+/paid only).
import PrimeVue from 'primevue/config';
import 'primevue/resources/themes/aura-light-indigo/theme.css';
import 'primevue/resources/primevue.min.css';

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.use(PrimeVue);
});
