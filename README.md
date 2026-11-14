# Invoice Manager — de-bloated (no payments, no ads/tracking)

A rebuild pipeline that takes **Invoice Manager (`com.invoiceapp`) 5.0.99** and produces
an APK with the **payment system (Google Play Billing) and advertising/tracking
permissions removed**, paying-premium entitlement unlocked, rebuilt and signed in CI.

> This is a modified build of a third-party app for personal/educational use. The
> original app is © Tacktile Systems Pvt Ltd. Not affiliated; not for redistribution.

## What the patch does

`patches/apply.py` (idempotent) edits an apktool-decoded tree:

1. **Removes the payment system & ad/tracking permissions** from `AndroidManifest.xml`:
   - `com.android.vending.BILLING`
   - `com.google.android.gms.permission.AD_ID`
   - `android.permission.ACCESS_ADSERVICES_{ATTRIBUTION,AD_ID,CUSTOM_AUDIENCE,TOPICS}`
   - `com.google.android.finsky.permission.BIND_GET_INSTALL_REFERRER_SERVICE`
   - drops the `com.google.android.play.billingclient.version` metadata
   - removes the `requiredSplitTypes`/`splitTypes` attributes (repacked as a single APK)
2. **Disables automatic tracking**: `com.facebook.sdk.AutoInitEnabled=false`,
   `firebase_analytics_collection_enabled=false`.
3. **Unlocks the paywall gate**: injects `com.oll.Premium.apply(Context)` into
   `com.invoiceapp.SimpleInvocieApplication.onCreate()`, which forces the entitlement
   flags the app reads from `TempAppSettingSharePref`
   (`TrialPeriodUserFlag`, `TrialPeriodServiceFlag`, `GetMoreInvoicesFlag`,
   `isPurchaseSuccessful`, `purchaseServerStatus`, far-future `TrialPeriodDays`).
4. **Folds the arm64 split's native libraries** (`libsqlite3x.so`, …) into the base APK
   so the single APK is runnable.
5. Fixes apktool's AnimatedVectorDrawable sub-resource names (`$name__N` → `_name__N`)
   that some `aapt2` builds reject.

## Note on "ads"
The app ships **no ad-network SDK** (no AdMob/AppLovin/Unity/ironSource/…). What this
patch removes on the "ads" side is the advertising-ID / AdServices permissions and the
Facebook/Firebase auto-tracking; the app's own upsell screens simply become unreachable
because the entitlement gate now reports "premium".

## Layout
```
base/            original base APK + arm64 split (input)
patches/
  apply.py       the patcher (manifest, smali hook, libs, AVD fix)
  Premium.smali  the injected entitlement-unlock class
scripts/build.sh decode -> patch -> build -> zipalign -> sign
.github/workflows/build.yml  CI
```

## Build locally
```bash
sudo apt-get install -y apktool openjdk-17-jdk   # + Android build-tools (zipalign, apksigner)
bash scripts/build.sh
# -> dist/invoiceapp-debloated.apk
```
Signing uses `KEYSTORE_BASE64` / `KEYSTORE_PASSWORD` / `KEY_ALIAS` / `KEY_PASSWORD`
env vars if present, otherwise a throwaway debug key is generated.

## Build on GitHub Actions
Push to `main`. The workflow decodes, patches, rebuilds, signs and uploads
`invoiceapp-debloated` as an artifact and to the `debloated-latest` release.
For a persistent signature set repo secrets:
`KEYSTORE_BASE64` (base64 of your .jks), `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD`.

## Caveats
- App code is R8-obfuscated; the unlock flips the local entitlement flags at startup.
  Server-validated cloud features can still be re-checked by the vendor backend.
- Re-signed with a different key — uninstall the Play version before installing
  (signature mismatch).
- Test on a spare device/emulator.
