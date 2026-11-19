# Reused material

The initial React interface, styling, avatars, template library, preview element
picker, guided display helpers, framework/design references and Ultimate Builder specialist playbooks were
adapted from the user's Appling checkout (Hermes-based), at commit
`776b6ab1f240e4bd88fbc1d2046c3792389858ad`.

The source repository's MIT notice is preserved in LICENSE (Nous Research,
2025). Attribution and license files embedded in specialist directories are
preserved; consult those notices before redistributing their reference assets.

The new controller, project store and engine adapters do not depend on Hermes.

The optional WhatsApp sidecar uses the upstream MIT-licensed
[WhiskeySockets/Baileys](https://github.com/WhiskeySockets/Baileys) package
(`baileys`, pinned to `7.0.0-rc14`). Its package and dependency notices are
provided with installation; the package is not vendored into this checkout.
Baileys is independent of WhatsApp/Meta. The sidecar and phone controller are
new Appling code rather than a copy of Hermes's messaging gateway.
