#!/usr/bin/env python3
"""Patch an apktool-decoded Invoice Manager (com.invoiceapp) tree.

Removes the payment system (Google Play Billing) + advertising/tracking
permissions, disables Facebook/Firebase auto-tracking, and forces the
subscription entitlement flags so the paywall gate is satisfied.

Idempotent: safe to run more than once.

Usage: apply.py <decoded_dir> [split_apk_for_native_libs]
"""
import os
import re
import sys
import zipfile

DECODED = sys.argv[1] if len(sys.argv) > 1 else "work"
SPLIT = sys.argv[2] if len(sys.argv) > 2 else None
HERE = os.path.dirname(os.path.abspath(__file__))

MANIFEST = os.path.join(DECODED, "AndroidManifest.xml")
APP_SMALI = os.path.join(
    DECODED, "smali_classes2/com/invoiceapp/SimpleInvocieApplication.smali"
)

DROP_PERMISSIONS = [
    '<uses-permission android:name="com.android.vending.BILLING"/>',
    '<uses-permission android:name="com.google.android.finsky.permission.BIND_GET_INSTALL_REFERRER_SERVICE"/>',
    '<uses-permission android:name="com.google.android.gms.permission.AD_ID"/>',
    '<uses-permission android:name="android.permission.ACCESS_ADSERVICES_ATTRIBUTION"/>',
    '<uses-permission android:name="android.permission.ACCESS_ADSERVICES_AD_ID"/>',
    '<uses-permission android:name="android.permission.ACCESS_ADSERVICES_CUSTOM_AUDIENCE"/>',
    '<uses-permission android:name="android.permission.ACCESS_ADSERVICES_TOPICS"/>',
]


def patch_manifest():
    s = open(MANIFEST, encoding="utf-8").read()
    orig = s

    out = []
    removed = 0
    for line in s.split("\n"):
        if line.strip() in (p.strip() for p in DROP_PERMISSIONS):
            removed += 1
            continue
        out.append(line)
    s = "\n".join(out)

    # stop Facebook SDK auto-tracking
    s = s.replace(
        'android:name="com.facebook.sdk.AutoInitEnabled" android:value="true"',
        'android:name="com.facebook.sdk.AutoInitEnabled" android:value="false"',
    )
    # stop Firebase analytics collection
    if "firebase_analytics_collection_enabled" not in s:
        s = s.replace(
            '<meta-data android:name="firebase_performance_logcat_enabled" android:value="true"/>',
            '<meta-data android:name="firebase_performance_logcat_enabled" android:value="false"/>\n'
            '        <meta-data android:name="firebase_analytics_collection_enabled" android:value="false"/>',
        )
    # drop Play Billing client version metadata
    s = s.replace(
        '        <meta-data android:name="com.google.android.play.billingclient.version" android:value="8.0.0"/>\n',
        "",
    )
    # this is now a single (unsplit) apk
    s = s.replace(' android:requiredSplitTypes="base__abi"', "")
    s = re.sub(r'\s+android:splitTypes=""', "", s)

    if s != orig:
        open(MANIFEST, "w", encoding="utf-8").write(s)
    print(f"[manifest] removed {removed} permission(s)")


def patch_oncreate():
    if not os.path.exists(APP_SMALI):
        print("[oncreate] !! SimpleInvocieApplication.smali not found")
        return
    s = open(APP_SMALI, encoding="utf-8").read()
    if "Lcom/oll/Premium;->apply" in s:
        print("[oncreate] already hooked")
        return
    anchor = (
        "    .line 1\n"
        "    invoke-super {p0}, Landroid/app/Application;->onCreate()V\n"
    )
    inject = (
        anchor
        + "\n    invoke-static {p0}, Lcom/oll/Premium;->apply(Landroid/content/Context;)V\n"
    )
    if anchor not in s:
        # fall back: right after the super call anywhere
        m = re.search(r"(\n(\s*)invoke-super \{p0\}, Landroid/app/Application;->onCreate\(\)V\n)", s)
        if not m:
            print("[oncreate] !! anchor not found")
            return
        s = s[: m.end(1)] + f"{m.group(2)}invoke-static {{p0}}, Lcom/oll/Premium;->apply(Landroid/content/Context;)V\n" + s[m.end(1):]
    else:
        s = s.replace(anchor, inject, 1)
    open(APP_SMALI, "w", encoding="utf-8").write(s)
    print("[oncreate] hooked Premium.apply()")


def install_helper():
    dst = os.path.join(DECODED, "smali_classes2/com/oll/Premium.smali")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    src = os.path.join(HERE, "Premium.smali")
    with open(src, encoding="utf-8") as fh, open(dst, "w", encoding="utf-8") as out:
        out.write(fh.read())
    print("[helper] installed com/oll/Premium.smali")


def fix_avd_resource_names():
    """aapt2 in some builds rejects AnimatedVectorDrawable sub-resource names
    that start with '$' (e.g. '$avd_hide_password__0'). Rename them to a valid
    '_...' identifier consistently across file names, public.xml and refs."""
    pat = re.compile(r"\$([A-Za-z0-9_]+__[0-9]+)")
    res = os.path.join(DECODED, "res")
    renamed = fixed = 0
    for dirpath, _, files in os.walk(res):
        for fn in files:
            if "$" in fn:
                new = pat.sub(r"_\1", fn)
                if new != fn:
                    os.rename(os.path.join(dirpath, fn), os.path.join(dirpath, new))
                    renamed += 1
    for dirpath, _, files in os.walk(res):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                s = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, IsADirectoryError):
                continue
            if "$" in s:
                ns = pat.sub(r"_\1", s)
                if ns != s:
                    open(p, "w", encoding="utf-8").write(ns)
                    fixed += 1
    print(f"[avd] renamed {renamed} file(s), patched {fixed} ref file(s)")


def install_native_libs():
    if not SPLIT or not os.path.exists(SPLIT):
        print("[libs] no split supplied, skipping")
        return
    with zipfile.ZipFile(SPLIT) as z:
        n = 0
        for name in z.namelist():
            if name.startswith("lib/") and not name.endswith("/"):
                dst = os.path.join(DECODED, name)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as out:
                    out.write(z.read(name))
                n += 1
    print(f"[libs] installed {n} native librar(ies) from split")


if __name__ == "__main__":
    patch_manifest()
    fix_avd_resource_names()
    install_helper()
    patch_oncreate()
    install_native_libs()
    print("done")
