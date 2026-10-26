# root-harness on your phone

`dist/` is the phone build of the one root-harness interface (source in
`../ui-src/`, built with `npm run build` there). The computer serves it on your
Wi-Fi when *Use from my phone* is on; any HTTPS static host works too, since
the files hold no secret: everything is computed on the phone.
