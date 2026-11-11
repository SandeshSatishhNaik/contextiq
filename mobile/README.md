# Phone assistants

Both integrations call the same read-only endpoint, `POST /api/voice` (header `X-Voice-Token`).
The server refuses "pay / send / approve / confirm" by voice — money actions need the screen.

| Platform | File | Status |
| --- | --- | --- |
| Siri (iOS 17+, App Intents) | `ios/AskContextIQIntent.swift` | Written, **not built or tested** (needs Xcode) |
| Siri without an app | Shortcuts recipe in the main README | Works today with any public URL |
| Google Assistant / Gemini (App Actions) | `android/shortcuts.xml`, `android/AskActivity.kt` | Written, **not built or tested** (needs Android Studio) |
| Any browser | microphone in the web app | Works today (Chrome, Edge, Safari) |
