const apiOrigin = process.env.HERMES_API_ORIGIN || 'http://127.0.0.1:9119'
const apiProxyTarget = `${apiOrigin.replace(/\/$/, '')}/api`

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  modules: ['@nuxt/ui', '@comark/nuxt'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  runtimeConfig: {
    public: {
      hermesSessionToken: process.env.NUXT_PUBLIC_HERMES_SESSION_TOKEN || ''
    }
  },
  app: {
    head: {
      title: 'Hermes Agent Chat',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' }
      ]
    }
  },
  nitro: {
    preset: 'static',
    devProxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true
      }
    }
  },
  typescript: {
    strict: true
  }
})
