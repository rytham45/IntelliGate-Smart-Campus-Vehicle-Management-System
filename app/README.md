# IntelliGate Android

Open this folder (`app/` in the repository) in Android Studio. Its nested `app/`
folder is the Android application module.

Kotlin, Jetpack Compose, Material 3 Expressive, Koin, ViewModel and StateFlow.
Android 11+, JDK 21 and Android SDK 37 are required.

## Scan flow

The installed camera captures the full photo. Android corrects orientation,
resizes to a maximum 2048-pixel edge without upscaling, and tries JPEG qualities
90, 85 and 80 to fit within 500,000 bytes. Otherwise it asks for a retake.

Anonymous Firebase sign-in happens automatically. Android writes:

```text
scan_images/{uid}/{scanId}
```

```json
{"image": "<Base64 JPEG>", "created_at": "<Firebase server timestamp in milliseconds>"}
```

It listens to `scan_results/{uid}/{scanId}`. The backend returns `status`:
`complete`, `review` or `error`. Complete results require `plate_number` and a
Boolean `is_valid`; owner `name`, `role` and `has_pass` are optional.
Only `is_valid` decides approval. The backend recognizes plates and checks its
vehicle database; Android does not call an AI API or calculate validity.

Each retry gets a new scan ID. The overall timeout is 60 seconds. Android attempts
request/result deletion and registers disconnect cleanup. Backend cleanup remains
necessary. Scan state stays in the ViewModel without process-death restoration.
Local camera files are temporary.

## Setup and build

Register `com.liftley.intelligate` in Firebase project `intelli-gate`, enable
Anonymous Authentication, and place the downloaded Android configuration at
`app/google-services.json` inside this Android project. This file is ignored.

Database URL:
`https://intelli-gate-default-rtdb.asia-southeast1.firebasedatabase.app`

Review/publish `firebase/database.rules.json` separately; adding it to Git does
not deploy rules. Run exactly one compatible scan worker on the backend laptop,
with its recognition service configured and its clock synchronized. The phone and
backend need internet, but do not need the same Wi-Fi.

```powershell
.\gradlew.bat :app:assembleDebug :app:lintDebug
```

The app builds without Firebase configuration, but live scans require it.
No credentials, database or backend environment are included.
See `docs/BACKEND_CONTRACT.md` for the complete integration contract.
