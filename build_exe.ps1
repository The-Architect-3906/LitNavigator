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
