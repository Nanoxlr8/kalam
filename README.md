# Kalam · كلام

A local take on Wispr Flow for Windows. Press a hotkey in any app, speak Arabic, English or a mix of both, and the cleaned-up text is typed where your cursor is. It runs on the Gemini API free tier.

## Run

```
pip install -r requirements.txt
pythonw app.py            # or double-click Kalam.vbs
powershell -ExecutionPolicy Bypass -File install_shortcut.ps1          # Desktop + Start Menu shortcut
powershell -ExecutionPolicy Bypass -File install_shortcut.ps1 -Startup # ...and launch at sign-in
```

## Use

| Action | Key |
|---|---|
| Start/stop (tap) | **F8** |
| Push-to-talk | hold **F8** and release when you finish |
| Cancel | **Esc** |

You can change the hotkey in Settings.

- **Smart**: removes fillers (امم، um) and false starts, adds punctuation, and turns spoken lists (واحد، اتنين) into numbered lists.
- **Exact**: near-verbatim, with punctuation added.
- **Rewrite**: turns what you said into polished text. It adapts to the app you're in, for example an email tone in Outlook.
- **Snippets**: define a trigger phrase for text you use often.
- **Dictionary**: spelling hints (ZATCA, names) plus replacements that run after transcription.

## Model choice (benchmarked 2026-09-26 on a 23s mixed Arabic/English clip)

| Model | API latency | Notes |
|---|---|---|
| **gemini-3.5-flash-lite** (default) | ~1.8s | Cheapest and fastest. Mixed script and lists are correct. |
| gemini-3.1-flash-lite (fallback) | ~2.5s | Has its own free quota. |
| gemini-3.8-flash | ~5s | Best quality, but a small free quota. Good for Rewrite. |
| gemini-2.5-flash / -lite | — | Retired for new users (404). |
| gemini-3.5-transcribe | — | Not available on the free tier here. |

Latency tricks:
- Audio is compressed with Opus (about 6× smaller than WAV).
- Audio is encoded while you talk, so stopping adds only ~25 ms. Silent recordings are skipped.
- The HTTPS connection is warmed while you talk and reused afterwards.
- Thinking is set to minimal and the response is streamed.

## Rate limits and latency in the UI

- **Home → Rate limits**: live RPM, RPD and TPM gauges for the active model, plus a countdown to the daily reset (midnight Pacific).
- The starting limits are estimates. When Google returns a 429, Kalam reads the real quota from the error and saves it.
- **Home → Latency**: the time from stop to pasted text, split into first word, full answer, encode and paste. Also shows a sparkline, p50/p90 and a free Ping for network RTT.
- **Usage & limits**: requests, tokens, what it would cost on the paid tier, per-model latency, and editable limits.

Data (settings, API key, history DB) lives in `%APPDATA%\Kalam`. Nothing leaves your PC except the audio sent to Gemini.
