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

python -m PyInstaller --noconfirm --name LitNavigator --console `
  --add-data "data/seed;data/seed" `
  --add-data "litnav/ui/templates;litnav/ui/templates" `
  --collect-all langgraph `
  --collect-all langgraph_checkpoint `
  --collect-all langchain_core `
  --collect-submodules uvicorn `
  run_litnav.py

# Ship the user-facing .env template + quick-start NEXT TO the exe (run_litnav reads .env
# from the exe's own directory). Then zip the folder into a GitHub Release asset.
Copy-Item packaging/env.example.txt   dist/LitNavigator/.env.example    -Force
Copy-Item packaging/README-FIRST.txt  dist/LitNavigator/README-FIRST.txt -Force
Compress-Archive -Path dist/LitNavigator/* -DestinationPath dist/LitNavigator-windows.zip -Force
Write-Host "Release bundle ready: dist/LitNavigator-windows.zip"
