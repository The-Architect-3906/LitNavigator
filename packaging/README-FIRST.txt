LitNavigator — quick start
==========================

1) RUN IT
   Double-click  LitNavigator.exe
   A browser opens at  http://127.0.0.1:8000/tutor
   Type a learning goal (e.g. "I want to understand ReAct") and chat with the tutor:
   it plans a route from the papers, teaches from cited evidence, quizzes you, catches
   misconceptions and re-teaches, and induces new scaffolding when you ask about something
   off the curated map. Toggle the "Glass box" view to watch the agent's steps live.

   By default it runs OFFLINE — the full agentic flow, no API key, $0.

2) (OPTIONAL) ENABLE REAL AI TEACHING
   - Rename  ".env.example"  to  ".env"   (exactly .env)
   - Open it and paste your OpenAI API key after  LITNAV_LLM_API_KEY=
   - Re-run LitNavigator.exe — teaching is now generated live by gpt-4o-mini.

It only teaches what its paper pack supports; ask about something outside that and it
tells you honestly. Built for the ICCSE 2026 Agentic AI Competition.
