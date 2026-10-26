// One source, two places: the computer's window and the phone's web app.
import { build } from 'esbuild'
import { copyFileSync, writeFileSync, mkdirSync } from 'fs'

const page = (extra) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
${extra}<title>root-harness</title><link rel="stylesheet" href="style.css"></head>
<body><script src="app.js"></script></body></html>
`
const cibles = [
  { out: '../rootharness/ui', entry: 'host-computer.js', head: '' },
  { out: '../mobile/dist', entry: 'host-phone.js', head: `<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><meta name="apple-mobile-web-app-title" content="root-harness">
<meta name="theme-color" content="#11131c"><link rel="manifest" href="manifest.webmanifest"><link rel="apple-touch-icon" href="icon-180.png"><link rel="icon" href="icon-192.png">
` },
]
for (const c of cibles) {
  mkdirSync(c.out, { recursive: true })
  await build({ entryPoints: [c.entry], bundle: true, minify: true, format: 'iife', target: ['safari15', 'chrome100'], outfile: c.out + '/app.js', logLevel: 'warning' })
  copyFileSync('style.css', c.out + '/style.css')
  writeFileSync(c.out + '/index.html', page(c.head))
  copyFileSync('assets/root-head.svg', c.out + '/root-head.svg')
  if (c.entry === 'host-computer.js') copyFileSync('../mobile/dist/icon-512.png', c.out + '/icon.png')
}
writeFileSync('../mobile/dist/manifest.webmanifest', JSON.stringify({ name: 'root-harness', short_name: 'root-harness', start_url: './', display: 'standalone',
  background_color: '#11131c', theme_color: '#11131c', icons: [{ src: 'icon-192.png', sizes: '192x192', type: 'image/png' }, { src: 'icon-512.png', sizes: '512x512', type: 'image/png' }] }))
// online (Cloudflare Pages): a few safety headers for the phone app
writeFileSync('../mobile/dist/_headers', `/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: no-referrer
  Permissions-Policy: camera=(self), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=31536000
/app.js
  Cache-Control: no-cache
/index.html
  Cache-Control: no-cache
`)
console.log('built: rootharness/ui and mobile/dist')
