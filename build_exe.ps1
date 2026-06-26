# Build the standalone LitNavigator desktop demo (Windows).
#
#   pip install pyinstaller
#   ./build_exe.ps1
#
# Output: dist/LitNavigator/LitNavigator.exe  (a folder you can zip and share).
# Double-click the exe -> starts the local server (offline by default) and opens the browser.
# To enable live LLM teaching, drop a .env next to the exe:
#     LITNAV_LLM_PROVIDER=openai
#     LITNAV_LLM_API_KEY=sk-...
#
# Offline by default (no key) runs the full agentic flow deterministically at $0.

# NOTE: litellm + tiktoken (with the tiktoken_ext plugins) MUST be collected, or live mode
# silently falls back to the offline path inside the frozen exe — tiktoken can't find the
# `cl100k_base` encoding ("Unknown encoding cl100k_base. Plugins found: []") because the
# `tiktoken_ext` namespace package isn't picked up by default. The hidden-imports below register it.
python -m PyInstaller --noconfirm --name LitNavigator --console `
  --add-data "data/seed;data/seed" `
  --add-data "litnav/ui/templates;litnav/ui/templates" `
  --collect-all langgraph `
  --collect-all langgraph_checkpoint `
  --collect-all langchain_core `
  --collect-all litellm `
  --collect-all tiktoken `
  --collect-submodules uvicorn `
  --hidden-import tiktoken_ext `
  --hidden-import tiktoken_ext.openai_public `
  run_litnav.py

# Ship the user-facing .env template + quick-start NEXT TO the exe (run_litnav reads .env
# from the exe's own directory). Then zip the folder into a GitHub Release asset.
Copy-Item packaging/env.example.txt   dist/LitNavigator/.env.example    -Force
Copy-Item packaging/README-FIRST.txt  dist/LitNavigator/README-FIRST.txt -Force
Compress-Archive -Path dist/LitNavigator/* -DestinationPath dist/LitNavigator-windows.zip -Force
Write-Host "Release bundle ready: dist/LitNavigator-windows.zip"
