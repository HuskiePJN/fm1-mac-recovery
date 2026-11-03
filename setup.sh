#!/bin/sh
# FM-1 Mac Recovery: one-time setup. Safe to run again; it only adds what is missing.
set -e
cd "$(dirname "$0")"
LOADER_URL="https://raw.githubusercontent.com/kagaimiq/jl-uboot-tool/adb3f18889e88ac512ce0a3c4d8cc3d3cb30696a/data/loaderblobs/usb/wl82loader.bin"
LOADER_SHA="d41da6126760c9d66660bcc0cac8d27d221806c5e369a8036921efe68dca5376"

if ! xcode-select -p >/dev/null 2>&1; then
    echo "Apple's command line tools are missing. Run this, finish the installer, then run sh setup.sh again:"
    echo "  xcode-select --install"
    exit 1
fi
if [ ! -f /opt/homebrew/lib/libusb-1.0.dylib ] && [ ! -f /usr/local/lib/libusb-1.0.dylib ]; then
    if ! command -v brew >/dev/null 2>&1; then
        echo "libusb is needed, and Homebrew installs it. Install Homebrew from https://brew.sh, then run sh setup.sh again."
        exit 1
    fi
    echo "Installing libusb with Homebrew..."
    brew install libusb
fi
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
mkdir -p loader
if [ ! -f loader/wl82loader.bin ] || [ "$(shasum -a 256 loader/wl82loader.bin | cut -d' ' -f1)" != "$LOADER_SHA" ]; then
    echo "Downloading JieLi's flash loader (jl-uboot-tool, MIT)..."
    curl -fsSLo loader/wl82loader.bin "$LOADER_URL"
    if [ "$(shasum -a 256 loader/wl82loader.bin | cut -d' ' -f1)" != "$LOADER_SHA" ]; then
        rm -f loader/wl82loader.bin
        echo "The downloaded loader does not match its known fingerprint. Removed it; nothing else changed."
        exit 1
    fi
fi
echo "Setup done. Next: put the FM-1 in download mode (step 3), then:"
echo "  sudo .venv/bin/python fm1_recover.py backup"
