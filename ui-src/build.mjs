// One source, two places: the computer's window and the phone's web app.
import { build } from 'esbuild'
import { copyFileSync, writeFileSync, mkdirSync } from 'fs'

// No inline script, no plugin, no <base>: a text from the network that slips into the page cannot run.
// The computer's window also allows eval: pywebview builds its bridge to Python with new Function().
const csp = (evalOk) => ["default-src 'self'", "script-src 'self'" + (evalOk ? " 'unsafe-eval'" : ''), "object-src 'none'", "base-uri 'none'", "form-action 'none'",
  "frame-src 'none'", "style-src 'self' 'unsafe-inline'", "img-src 'self' https: data: blob:", "media-src 'self' https: data: blob:", "font-src 'self' data:",
  "connect-src 'self' https: wss:", "worker-src 'self'", "manifest-src 'self'"].join('; ')
const page = (extra, evalOk) => `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${csp(evalOk)}">
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
  writeFileSync(c.out + '/index.html', page(c.head, c.entry === 'host-computer.js'))
  copyFileSync('assets/root-head.svg', c.out + '/root-head.svg')
  for (const f of ['porte.jpg', 'porte-1.jpg', 'porte-2.jpg', 'porte-3.jpg', 'porte-4.jpg', 'porte-5.jpg']) copyFileSync('assets/' + f, c.out + '/' + f)
  if (c.entry === 'host-computer.js') copyFileSync('../mobile/dist/icon-512.png', c.out + '/icon.png')
  else copyFileSync('assets/sw.js', c.out + '/sw.js')
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
/
  Cache-Control: no-cache
/style.css
  Cache-Control: no-cache
/app.js
  Cache-Control: no-cache
/index.html
  Cache-Control: no-cache
/sw.js
  Cache-Control: no-cache
`)
console.log('built: rootharness/ui and mobile/dist')
