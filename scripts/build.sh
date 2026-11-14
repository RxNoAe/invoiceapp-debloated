#!/usr/bin/env bash
# Decode -> patch -> rebuild -> zipalign -> sign  the de-bloated Invoice Manager APK.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# apktool needs a generous heap on large apps (decode + smali + aapt2 link).
export JAVA_OPTS="${JAVA_OPTS:--Xmx6g -XX:+UseSerialGC}"

BASE="base/com.invoiceapp.apk"
SPLIT="base/config.arm64_v8a.apk"
WORK="work"
DIST="dist"

echo ":: group::locate Android build-tools"
find_bt() {
  local tool="$1"
  if command -v "$tool" >/dev/null 2>&1; then command -v "$tool"; return; fi
  for d in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" "$HOME/Android/Sdk" /usr/lib/android-sdk; do
    [ -n "$d" ] || continue
    local hit
    hit=$(ls -1 "$d"/build-tools/*/"$tool" 2>/dev/null | sort -V | tail -1 || true)
    [ -n "$hit" ] && { echo "$hit"; return; }
  done
}
ZIPALIGN="$(find_bt zipalign || true)"
APKSIGNER="$(find_bt apksigner || true)"
echo "zipalign : ${ZIPALIGN:-<missing>}"
echo "apksigner: ${APKSIGNER:-<missing>}"
echo ":: endgroup"

# Prefer invoking apktool.jar directly so our heap setting is applied.
# (The distro `apktool` wrapper ignores JAVA_OPTS and runs its own default heap.)
APKTOOL_JAR=""
for c in /usr/share/apktool/apktool.jar /usr/share/java/apktool.jar /usr/share/java/Apktool.jar; do
  [ -f "$c" ] && APKTOOL_JAR="$c" && break
done
if [ -z "$APKTOOL_JAR" ]; then
  APKTOOL_JAR="$ROOT/apktool.jar"
  if [ ! -f "$APKTOOL_JAR" ]; then
    echo "downloading apktool jar..."
    curl -sSL --retry 3 -o "$APKTOOL_JAR" \
      "https://github.com/iBotPeaches/Apktool/releases/download/v2.11.1/apktool_2.11.1.jar"
  fi
fi
APKTOOL="java $JAVA_OPTS -jar $APKTOOL_JAR"
echo "apktool cmd: $APKTOOL"

echo ":: group::decode"
rm -rf "$WORK" "$DIST"
mkdir -p "$DIST"
$APKTOOL d -f -o "$WORK" "$BASE"
echo ":: endgroup"

echo ":: group::patch"
python3 patches/apply.py "$WORK" "$SPLIT"
echo ":: endgroup"

echo ":: group::build"
$APKTOOL b -o "$DIST/app-unsigned.apk" "$WORK"
echo ":: endgroup"

echo ":: group::sign"
# Keystore: from env (CI secrets) or an auto-generated throwaway.
KEYSTORE="${KEYSTORE_PATH:-$ROOT/keystore.jks}"
if [ -n "${KEYSTORE_BASE64:-}" ]; then
  echo "$KEYSTORE_BASE64" | base64 -d > "$KEYSTORE"
  KS_PASS="${KEYSTORE_PASSWORD:-android}"
  K_ALIAS="${KEY_ALIAS:-release}"
  K_PASS="${KEY_PASSWORD:-$KS_PASS}"
elif [ ! -f "$KEYSTORE" ]; then
  echo "no keystore supplied -> generating throwaway debug key"
  KEYSTORE="$ROOT/debug.jks"
  KS_PASS="android"; K_ALIAS="androiddebugkey"; K_PASS="android"
  keytool -genkeypair -v -keystore "$KEYSTORE" -storepass "$KS_PASS" \
    -alias "$K_ALIAS" -keypass "$K_PASS" -keyalg RSA -keysize 2048 \
    -validity 10000 -dname "CN=debloated,O=local,C=US" >/dev/null 2>&1
else
  KS_PASS="${KEYSTORE_PASSWORD:-android}"
  K_ALIAS="${KEY_ALIAS:-release}"
  K_PASS="${KEY_PASSWORD:-$KS_PASS}"
fi

if [ -n "$ZIPALIGN" ]; then
  "$ZIPALIGN" -f -p 4 "$DIST/app-unsigned.apk" "$DIST/app-aligned.apk"
else
  cp "$DIST/app-unsigned.apk" "$DIST/app-aligned.apk"
fi

if [ -n "$APKSIGNER" ]; then
  "$APKSIGNER" sign --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" \
    --ks-key-alias "$K_ALIAS" --key-pass "pass:$K_PASS" \
    --out "$DIST/invoiceapp-debloated.apk" "$DIST/app-aligned.apk"
  "$APKSIGNER" verify --print-certs "$DIST/invoiceapp-debloated.apk"
else
  cp "$DIST/app-aligned.apk" "$DIST/invoiceapp-debloated.apk"
fi
rm -f "$DIST/app-unsigned.apk" "$DIST/app-aligned.apk"
echo ":: endgroup"

ls -la "$DIST"
echo "DONE -> $DIST/invoiceapp-debloated.apk"
