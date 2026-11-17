---
name: mobile-expo
description: Build phone apps the owner tests live with Expo Go.
---

# Mobile Expo Skill

Builds one app for iPhone and Android with Expo (React Native) so the owner
can test it on their own phone from day one: they scan a QR code in Appling's
preview panel with the free Expo Go app and every change reloads on the phone
within seconds. It does not publish to the app stores (that needs the owner's
own Apple / Google developer accounts — a separate, later step).

## When to Use

- The setup message lists `platforms` with `phone`.
- The owner asks for an iPhone or Android app, or "an app on my phone".

## Prerequisites

- Node 20+ and npm (`node -v`).
- The owner has **Expo Go** installed (App Store / Google Play) and their phone
  on the same Wi-Fi as this computer.

## How to Run

Scaffold in the project folder on the **current** Expo SDK (Expo Go on iPhone
only runs the latest one):

```
npx create-expo-app@latest . --template blank-typescript --yes
npx expo install <package>     # always, never plain npm install, for native packages
```

Do not run `expo start` yourself for the owner: Appling's preview panel starts
it and shows the QR code. For your own checks use `npx expo export --platform web`
(or `npx expo start --web` briefly) and the site check, plus `npx tsc --noEmit`.

## Quick Reference

| Need | Use (Expo Go compatible) |
|---|---|
| Screens and navigation | `expo-router` (file-based) |
| Saving data on the phone | `expo-sqlite` or `@react-native-async-storage/async-storage` |
| Camera / photos | `expo-camera`, `expo-image-picker` |
| Location / maps | `expo-location`, `react-native-maps` |
| Notifications | `expo-notifications` (local ones work in Expo Go) |
| Haptics, sharing, clipboard | `expo-haptics`, `expo-sharing`, `expo-clipboard` |
| Icons and fonts | `@expo/vector-icons`, `expo-font` |

## Procedure

1. **Plan for a phone.** One-handed use, thumb-reachable actions at the
   bottom, 44 pt touch targets, safe areas (`react-native-safe-area-context`),
   keyboard that never hides the field being typed in, light and dark mode.
   Pick colours with `ultimate-builder:color-and-ux`.
2. **Stay inside Expo Go.** Before adding any library, check it is in the
   Expo SDK or marked "Expo Go compatible". If a feature truly needs native
   code outside Expo Go (some payment SDKs, Bluetooth, custom native modules),
   stop and tell the owner in plain words: it will need a "development build"
   (an extra install step on their phone) — do not add it silently.
3. **Build screen by screen.** After each screen: type-check, export for web
   and run the site check at phone size, then ask the owner to look on their
   phone ("Scan the QR in the preview panel — the new screen is live").
4. **Real-device checks** the owner can do in a minute: rotate, dark mode,
   kill and reopen the app (data still there), airplane mode (sensible
   message, no crash).
5. **Finish.** `app.json` has the real app name, icon and splash (ask for a
   logo; otherwise a simple generated one), commit, and report what to try on
   the phone plus what publishing would need later.

## Pitfalls

- Expo Go on iPhone supports only the latest SDK: never pin an old one.
- `npm install` of native packages picks versions Expo Go can't run — use
  `npx expo install`.
- Web-only APIs (`window`, `localStorage`, DOM) crash on the phone.
- Phones and computers on different Wi-Fi networks can't connect; tell the
  owner to join the same network (or ask Appling to use a tunnel).
- Large images in the bundle make reloads slow: resize assets.

## Verification

- `npx tsc --noEmit` passes and `npx expo export --platform web` succeeds.
- The site check passes at phone size on the web export.
- The owner confirmed the app runs in Expo Go on their phone, or the report
  says plainly that this check is still waiting for them.
