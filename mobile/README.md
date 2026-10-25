# root-harness on your phone

A small web app that turns your phone into a remote for root-harness running
on your computer. Claude Code cannot run on a phone, so the agent keeps running
on the computer (your plan, your tools); the phone signs in with your pseudo and
password and talks to it through sealed Nostr messages (see
`rootharness/remote.py`). No port to open, no server of ours.

- Build: `npm install && npm run build` (outputs `dist/app.js`).
- Try it: turn on **Settings, Phone, Use from my phone** in root-harness; it
  serves `dist/` on your Wi-Fi and shows the address to open on your phone.
- To use it from anywhere, host `dist/` on any HTTPS static host (GitHub Pages,
  for instance): the files hold no secret, everything is computed on the phone.
- Siri: a Shortcut can open `<your address>/#ask=<text>` to prefill a message.
