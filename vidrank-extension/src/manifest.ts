import { defineManifest } from '@crxjs/vite-plugin'
import packageData from '../package.json'

export default defineManifest({
  manifest_version: 3,
  name: 'VidRank',
  version: packageData.version,
  description: packageData.description,
  key: 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAipqFG5q165s5p4lRvBWnyo59a4GBOG/W7eZtaUgCzcImnnkEv/DWt4aUstIfRj5zTHcO64W07hsQvjMba/ufENRnd2b+iFpO+qbaYMrWpOhESRKvqyPBc0Vnkcq7efl/ugA0+qBQFMxs/PV/KOUqZSjVgbOszTOXsgfap6/3t+AzH7A6EVLRnvf0lY/hu3Y0QdaklpFE6pCp02t8CdMdR8YTBpa2GRCbdN7OdBYZ4s6HOyFIvLeCfM1mNMCBmOIYHBrTpDOL+OGssLUUYLR3ZutoJ4ChG9ElH1iTfdXTQfx9KbA/eAGHUGCGs5sheWQRwosenDl1EJvgq4/TE0/FfQIDAQAB',
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
    'http://localhost:8787/*',
  ],
  content_security_policy: {
    extension_pages:
      "script-src 'self'; object-src 'self'; connect-src 'self' https://*.workers.dev https://*.googleapis.com https://*.firebaseapp.com https://identitytoolkit.googleapis.com https://securetoken.googleapis.com http://localhost:8787",
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
