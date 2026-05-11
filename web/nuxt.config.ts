const defaultAcpCwd = process.env.HERMESUM_ACP_CWD || (process.cwd().endsWith('/web') ? process.cwd().slice(0, -4) : process.cwd())

export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: false },
  modules: ['@nuxt/ui', '@comark/nuxt'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  runtimeConfig: {
    hermesAcpCommand: process.env.HERMESUM_ACP_COMMAND || 'hermes',
    hermesAcpArgs: process.env.HERMESUM_ACP_ARGS ? process.env.HERMESUM_ACP_ARGS.split(' ').filter(Boolean) : ['acp'],
    hermesAcpCwd: defaultAcpCwd,
    public: {
      hermesSessionToken: process.env.NUXT_PUBLIC_HERMES_SESSION_TOKEN || ''
    }
  },
  app: {
    head: {
      title: 'Hermes Agent Chat',
      meta: [
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'theme-color', content: '#09090b' },
        { name: 'mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-title', content: 'Hermes' }
      ],
      link: [
        { rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' },
        { rel: 'icon', type: 'image/png', sizes: '16x16', href: '/icons/icon-16.png' },
        { rel: 'icon', type: 'image/png', sizes: '32x32', href: '/icons/icon-32.png' },
        { rel: 'icon', type: 'image/png', sizes: '48x48', href: '/icons/icon-48.png' },
        { rel: 'apple-touch-icon', sizes: '180x180', href: '/icons/icon-180.png' },
        { rel: 'manifest', href: '/site.webmanifest' }
      ]
    }
  },
  typescript: {
    strict: true
  }
})
