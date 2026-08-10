// Hey API (OpenAPI client generator) config.
// Generates a typed fetch client from the Django drf-spectacular schema.
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: '../backend/schema/openapi.json',
  output: 'app/lib/api',
  client: '@hey-api/client-fetch',
  plugins: ['@hey-api/typescript', '@hey-api/sdk'],
  // Strip the /api/v1 prefix from generated paths? Keep it — server handles it.
});
