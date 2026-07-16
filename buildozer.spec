[app]
title = WiFi Helper
package.name = wifihelper
package.domain = com.system

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 2.7
requirements = python3,kivy, python-telegram-bot==20.7, Pillow, requests
orientation = portrait
fullscreen = 1
icon.filename = icon.png

android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE, WAKE_LOCK, FOREGROUND_SERVICE
android.api = 30
android.minapi = 21
android.sdk_build_tools = 30.0.3          # Sabit kararlı sürüm (37 değil)
android.accept_sdk_license = True         # Lisansları otomatik kabul et
android.gradle_dependencies = 'com.android.support:support-annotations:28.0.0'

services = sonion:main.py

[buildozer]
log_level = 2
warn_on_root = 0
