#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
# Try to install Playwright chromium (may fail on free tier - that's OK, Sunbiz falls back to link)
playwright install chromium --with-deps 2>/dev/null || echo "Playwright chromium not installed - Sunbiz scraping disabled, using links instead"
