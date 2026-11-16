"""core/ai - everything that talks to the Claude API (AI requests screen). Spec: design/ai_requests.md.

settings.py  - ai_settings.json + the API key from .env
client.py    - send(): the ONE function in the app that calls the Claude API
docs.py      - documents -> what is sent (PDF document blocks, Excel / Word / text as text), the Schedule E template
logs.py      - AI_logs (cost log; corrections log later) - no client data
web.py       - the AI tab (routes) - registered by app.py
"""
