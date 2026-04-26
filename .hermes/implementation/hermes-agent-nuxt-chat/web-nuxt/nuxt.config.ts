export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },
  modules: ['@nuxt/ui', '@comark/nuxt'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  app: {
    head: {
      title: 'Hermes Agent Chat',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' }
      ]
    }
  },
  nitro: {
    preset: 'static'
  },
  typescript: {
    strict: true
  }
})
