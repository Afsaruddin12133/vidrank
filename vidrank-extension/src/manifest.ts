import { defineManifest } from '@crxjs/vite-plugin'
import packageData from '../package.json'

export default defineManifest({
  manifest_version: 3,
  name: 'VidRank',
  version: packageData.version,
  description: packageData.description,
  // Store public key — pins build ID to meafpgipnldknnbnmahbmbaakcmahogk.
  key: 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA3Lj/QpN1IW2byc/TOuE3eyFLR156AMfq0tB34pOf6XKdIAjPU6q4Z3SH0H8/yDpugrgzdiDobzFlOtPBMtNbYEz/gc/FhxliqRt4uGSPkQ6K4S7X0KRQLsfDygpPsjx4mLTM25s8rnlS1ssDtsHKhyxtdjv8OKleW+bqLYJhcGFbTAAOUulVmK0hcKl3Eoq/2Od9soXnddTp/G95ApuP6CGt6ag8prFdfvTJHAIR9yE8NXcwxkfx9j4JxSZ93zhALE2s4/Oa/vm7kSEZjJVtm7GVTbPyOsE5IvtL+f6gvANWChW8jbGJaRiQGvTrSwlZWFg7Wg65fT6LjsmdXAjGDQIDAQAB',
  permissions: ['storage', 'identity', 'sidePanel'],
  side_panel: {
    default_path: 'sidepanel.html',
  },
  host_permissions: [
    'https://studio.youtube.com/*',
    'https://*.workers.dev/*',
    'https://*.googleapis.com/*',
    'https://identitytoolkit.googleapis.com/*',
    'https://securetoken.googleapis.com/*',
    'https://edge.adsonbread.com/*',
    'https://*.adsonbread.com/*',
    'http://localhost:8787/*',
  ],
  content_security_policy: {
    extension_pages:
      "script-src 'self'; object-src 'self'; connect-src 'self' https://*.workers.dev https://*.googleapis.com https://*.firebaseapp.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://edge.adsonbread.com https://*.adsonbread.com http://localhost:8787 http://localhost:5173 ws://localhost:5173; img-src 'self' https: data: blob:;",
  },
  oauth2: {
    client_id: '5551217356-j4e9fsaadk4davrd08h6cqnh532km7bk.apps.googleusercontent.com',
    scopes: ['profile', 'email'],
  },
  background: {
    service_worker: 'src/background/index.ts',
    type: 'module',
  },
  content_scripts: [
    {
      matches: ['https://studio.youtube.com/*'],
      js: ['src/contentScript/ui.js', 'src/contentScript/content.js'],
      css: ['src/contentScript/content.css'],
      run_at: 'document_idle',
    },
  ],
  icons: {
    16: 'assets/icons/logo.png',
    48: 'assets/icons/logo.png',
    128: 'assets/icons/logo.png',
  },
  action: {
    default_popup: 'popup.html',
    default_title: 'VidRank',
    default_icon: {
      16: 'assets/icons/logo.png',
      48: 'assets/icons/logo.png',
      128: 'assets/icons/logo.png',
    },
  },
  web_accessible_resources: [
    {
      resources: ['assets/icons/logo.png'],
      matches: ['https://studio.youtube.com/*'],
    },
  ],
})
