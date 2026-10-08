# OmniTyper to Voxt feature mapping

This document maps each OmniTyper feature to its Voxt equivalent for roadmap issue sgl-project/sglang-omni#2537. A later PR removes `OmniTyper/`. A feature that is not in this document is lost at that time.

## Summary

Voxt covers 51 of 106 rows. 28 rows are partial and 16 rows are gaps. 11 rows have no role in Voxt.

| Status | Main branch | Unmerged PRs | Total |
| --- | ---: | ---: | ---: |
| `equivalent` | 45 | 6 | 51 |
| `partial` | 21 | 7 | 28 |
| `gap` | 12 | 4 | 16 |
| `obsolete` | 9 | 2 | 11 |
| **Total** | **87** | **19** | **106** |

Status meanings:

- `equivalent`: Voxt has the feature. Small differences are noted.
- `partial`: Voxt has part of the feature.
- `gap`: Voxt has no confirmed equivalent. The row states what was searched.
- `obsolete`: The feature exists only to support OmniTyper itself.

Effort: S is less than 1 day in 1 or 2 files. M is 1 to 3 days in several files. L is more than 3 days or crosses components.

### Fill (19 rows)

| ID | Feature | Status | Effort | Where |
| --- | --- | --- | --- | --- |
| ASR-11 | Remote sglang-omni server | `partial` | S | Make the API key optional for custom endpoints in RemoteASRFileRequests.swift:11-13. sglang-omni inference endpoints need no key. |
| ASR-3 | Model mlx-community/Qwen3-ASR-0.6B-4bit at a pinned revision | `partial` | S | Pin the revision for the Omni repo in MLXModelDownloadSupport.swift:243. |
| DEV-3 | Sign with a chosen identity so TCC grants survive rebuilds | `partial` | S | Let OmniDev.xcconfig take VOXT_CODE_SIGN_IDENTITY from Signing.local.xcconfig when it exists. |
| DIC-3 | CSV import and export | `partial` | S | Add CSV to DictionaryTransferManager. This also moves an exported OmniTyper dictionary into Voxt. |
| INS-1 | Paste at cursor, then restore the full clipboard | `partial` | S | Snapshot and restore all pasteboard item types in PasteboardTextWriter. |
| INS-2 | Transient and concealed pasteboard markers | `gap` | S | Set org.nspasteboard.TransientType and ConcealedType in PasteboardTextWriter. |
| INS-3 | Block secure fields and secure input | `gap` | S | Check IsSecureEventInputEnabled() and the AXSecureTextField subrole before start and before paste in TextOutputDelivery. |
| LLM-6 | Output guards: think stripping, tool-call rejection, finish_reason length is an error | `partial` | S | Treat finish_reason length as a failure in Core/LLM/RemoteLLMStreamingParser.swift. A cut-off cleanup must not reach the cursor. |
| MOD-3 | Voice edit: speak an instruction, replace the selected text | `partial` | S | In SessionTextIO.shouldPresentRewriteAnswerOverlay, return false when selected text exists. Add a Settings toggle for alwaysShowRewriteAnswerCard. |
| MOD-5 | Cleanup failure keeps the raw transcript and shows a warning | `partial` | S | In the TranscriptionFlow.swift:95 fallback branch, call showOverlayReminder (App/Recording/RecordingCaptureFlow.swift:411). |
| PR-2242-A | Stable local signing identity (sign.sh, test-signing.sh) | `partial` | S | Same fill as DEV-3. |
| PR-2250-B | Key names, Fn combinations, F1-F20 | `partial` | S | Add F1-F20 names in HotkeyPreferencePresentation.swift. |
| PR-2250-C | Keep the speech model loaded | `partial` | S | Add a Never option to the idle unload delay. The Omni server cold start is slow. |
| PRM-2 | Detect a stale Accessibility grant after a rebuild | `gap` | S | Store a was-trusted flag in AccessibilityPermissionManager. Show remove-and-re-add guidance when the flag is set and trust is gone. |
| STY-1 | Style presets: verbatim, clean, casual, formal, concise | `partial` | S | Add Casual, Formal and Concise presets in FeaturePromptPreset.swift. |
| HIS-3 | Original transcript next to the processed text | `partial` | M | Add an optional raw transcript field to TranscriptionHistoryEntry. Show it in the history detail sheet. |
| HIS-7 | Retry from saved audio and retry last | `gap` | M | Add Transcribe Again to history entries with audio. Reuse the final-pass path in MLXTranscriber. |
| PR-2434 | Dictionary hints in realtime session.update prompt | `gap` | M | Keep the server part of this PR. Add prompt to Voxt session.update and to sglang_omni_mlx realtime. |
| ASR-2 | Omni backend in a normal build (no environment variables) | `partial` | L | Resolve the Python runtime and backend directory without environment variables. Show the Omni engine in model settings. |

### Drop (25 rows)

| ID | Feature | Status | Reason |
| --- | --- | --- | --- |
| MOD-4 | Ask: spoken question, answer card, no insert, no web search | `partial` | Rewrite without a selection covers Ask. The Continue button adds follow-up turns. |
| AUD-6 | Panel shows elapsed time and Stop and Cancel buttons | `gap` | The hotkey stops the session and Esc cancels it. Mouse controls add little. |
| ASR-5 | Prepare ASR and Unload ASR buttons | `partial` | Prewarm and idle unload replace the manual buttons. Row PR-2250-C covers keep-loaded. |
| LLM-2 | Fetch the model list and choose a model | `partial` | A custom model ID and the connectivity Test cover setup. |
| LLM-3 | API key kept in memory only | `partial` | The Keychain is the macOS store for secrets. The user does not re-enter the key after each launch. |
| LLM-5 | Endpoint checks: URL validation, no redirects, 1 MiB response limit | `partial` | The credential rule covers the main risk. Response limits are general hardening, not a migration item. |
| DIC-4 | Learn a word from a history correction | `partial` | Auto learning and manual dictionary entry cover the need. |
| INS-4 | Direct AXSelectedText write in native apps | `gap` | Paste works in all apps. With INS-1 and INS-2 filled, paste has no clipboard cost. |
| INS-5 | Validate that the same editable field still has focus | `partial` | Voxt pastes at the current focus by design. History keeps every result. |
| INS-7 | Detect an ignored paste and fall back | `gap` | History keeps the result. The custom paste hotkey re-pastes it (TextOutputDelivery.swift:206). The detection is a heuristic. |
| INS-8 | Enable Accessibility in Chromium and Electron apps | `gap` | Voxt does not need field detection to paste. Selection reads use AppleScript and Cmd+C fallbacks (App/SelectedTextProbe.swift:30). |
| INS-9 | Auto paste off: copy only | `gap` | No request for copy-only output. autoCopyWhenNoFocusedInput covers the no-field case. |
| HIS-4 | Export history as JSON | `gap` | No migration flow depends on it. Meeting export and audio export cover the main data. |
| HIS-10 | Import OmniTyper data (library.json and Audio/) | `gap` | OmniTyper is a development demo. DIC-3 moves the dictionary. Old files stay on disk. |
| HIS-12 | Open the data folder | `gap` | The Logs sheet exports logs. The user picks the audio folder (AppPreferenceKey.swift:128). |
| APP-2 | Start, stop and cancel without a shortcut (menu items and Home button) | `partial` | Hotkeys start every Voxt session. Onboarding teaches the hotkey. |
| APP-3 | Appearance: light, dark or system | `partial` | The macOS appearance setting covers it. |
| APP-7 | macOS 14 support | `partial` | Voxt upstream targets macOS 15. A lower target is an app-wide port. |
| PR-2241 | Hugging Face endpoint setting and Use hf-mirror.com and retry | `partial` | The automatic probe covers the mirror case. |
| PR-2394 | Optional Hugging Face endpoint; invalid endpoint stops Prepare | `partial` | The automatic probe covers sgl-project/sglang-omni#2239. |
| PR-2242-C | Conflict messages: system, registered hotkeys, listener failure | `partial` | The static list covers the common system shortcuts. |
| PR-2242-D | ModelScope download source | `gap` | The hf-mirror.com probe covers mainland China access. |
| PR-2251-A | Hold the shortcut and move to pick a mode | `gap` | Separate hotkeys give direct mode access. |
| PR-2251-B | Review panel with pause, resume, Insert, Copy and Clear | `partial` | The answer card covers review. Meeting Notes covers long pausable capture. |
| PR-2251-C | Voice edit of the whole text box when nothing is selected | `gap` | Select-all before Rewrite gives the same result. |

### Remote sglang-omni server (row ASR-11)

OmniTyper cannot use a remote server. Voxt can, with three limits.

- OmniTyper starts a private local server. `ASRStream.swift:52` rejects any host other than 127.0.0.1.
- OmniTyper runs `sglang_omni.cli serve` with `SGLANG_USE_MLX=1`. It does not use the CUDA server.
- The Voxt `OpenAI Whisper` remote provider takes a full custom endpoint and a custom model ID (`Voxt/docs/RemoteModel.md:7-35`).
- It sends a 16 kHz mono WAV with `model`, `response_format=json`, `language` and `prompt` (`Transcription/RemoteASR/RemoteASRTextSupport.swift:49-67`).
- `sglang_omni/serve/speech_to_text.py:68-76` accepts these fields. So a sglang-omni `/v1/audio/transcriptions` endpoint works.

Limits:

1. Voxt requires a non-empty API key (`RemoteASRFileRequests.swift:11-13`). sglang-omni inference endpoints need no key. Enter any placeholder.
2. Voxt rejects plain HTTP with a key on a non-loopback host (`RemoteEndpointSecurityPolicy.swift:45-47`). Use HTTPS or an SSH tunnel to localhost.
3. Voxt does not stream to a remote `/v1/realtime`. The optional pseudo-realtime preview re-uploads WAV snapshots (`RemoteASRTranscriber.swift:264`).

The fill for ASR-11 makes the key optional. Then a LAN server over plain HTTP works without a tunnel.

## How to read the tables

- A bare `*.swift` name in the OmniTyper column is in `OmniTyper/Sources/OmniTyper/`.
- Other OmniTyper refs are relative to `OmniTyper/`.
- A Voxt ref that starts with `Voxt/` is relative to the repository root.
- Other Voxt refs are relative to `Voxt/Voxt/`.
- `sglang_omni/` and `sglang_omni_mlx/` refs are relative to the repository root.

## Voice modes and text processing

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **MOD-1** Dictate: speech to text, optional cleanup, insert at cursor | `AppModel.swift:264-310`<br>`backend/text_api.py:20-32` | `App/TranscriptionFlow.swift:95`<br>`Settings/TranscriptionTypes.swift:51`<br>Voxt runs cleanup only when EnhancementMode is not off. Both dictate without a text API. | `equivalent` | None. Voxt transcription with enhancement covers Dictate. |
| **MOD-2** Translate into a target language | `backend/text_api.py:21`<br>`Views.swift:212`<br>`PreferencesView.swift:45` | `Settings/Shell/AppPreferenceKey.swift:82-84`<br>`App/TranslationFlow.swift:124-130`<br>Voxt also translates selected text with the translation hotkey. | `equivalent` | None. Voxt translation covers this mode. |
| **MOD-3** Voice edit: speak an instruction, replace the selected text | `AppModel.swift:177`<br>`AppModel.swift:310`<br>`backend/text_api.py:22` | `App/SessionTextIO.swift:316-321`<br>`Windows/WaveformAnswerCard.swift:128`<br>Voxt Rewrite always shows an answer card. The user must click Inject into Current Input. OmniTyper replaces the selection directly. | `partial` | **Fill (S).** In SessionTextIO.shouldPresentRewriteAnswerOverlay, return false when selected text exists. Add a Settings toggle for alwaysShowRewriteAnswerCard. |
| **MOD-4** Ask: spoken question, answer card, no insert, no web search | `AppModel.swift:310`<br>`backend/text_api.py:24` | `Voxt/docs/Rewrite.md`<br>`Windows/WaveformAnswerCard.swift:124`<br>`Windows/WaveformAnswerCard.swift:151`<br>Rewrite without a selection gives the same answer card. With a selection, Voxt rewrites the selection. OmniTyper uses the selection as question context. | `partial` | **Drop.** Rewrite without a selection covers Ask. The Continue button adds follow-up turns. |
| **MOD-5** Cleanup failure keeps the raw transcript and shows a warning | `backend/worker.py:283-293` | `App/TranscriptionFlow.swift:95`<br>Voxt falls back to raw text. Voxt only logs the failure. The user sees no warning. | `partial` | **Fill (S).** In the TranscriptionFlow.swift:95 fallback branch, call showOverlayReminder (App/Recording/RecordingCaptureFlow.swift:411). |
| **MOD-6** Translate, edit and ask failures do not insert raw text | `backend/worker.py:283-293` | `App/TranslationFlow.swift:124-130`<br>`App/TranslationFlow.swift:384-389`<br>`App/TranslationFlow.swift:428-434`<br>Voxt shows Translation failed or Rewrite failed and commits no text. | `equivalent` | None. Same behavior. |

## Shortcuts

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **KEY-1** Custom global shortcut (default Ctrl+Option+Space) | `Store.swift:57-95`<br>`PreferencesView.swift:20-25`<br>`GlobalShortcut.swift` | `Hotkey/HotkeySupport.swift:144`<br>`Hotkey/HotkeySupport.swift:341-345`<br>The Voxt default is fn. Voxt also accepts mouse buttons. | `equivalent` | None. Voxt hotkeys cover this. |
| **KEY-2** Toggle or hold-to-talk | `PreferencesView.swift:26`<br>`AppModel.swift:100`<br>`GlobalShortcut.swift:160` | `Hotkey/HotkeySupport.swift:10-13`<br>`Hotkey/HotkeySupport.swift:115-131`<br>Voxt also has double-tap. | `equivalent` | None. Same behavior. |
| **KEY-3** Lone modifier shortcuts such as Fn | `ShortcutCapture.swift:30`<br>`GlobalShortcut.swift:21` | `Hotkey/HotkeySupport.swift:341-345`<br>`Hotkey/HotkeySupport.swift:430`<br>The Voxt default shortcut is the lone fn key. | `equivalent` | None. Same behavior. |
| **KEY-4** Hold release from the physical key state | `GlobalShortcut.swift:72` | `Hotkey/HotkeyManager.swift:120`<br>Both read CGEventSource key state. | `equivalent` | None. Same behavior. |
| **KEY-5** Re-enable the event tap after a timeout | `GlobalShortcut.swift:118` | `Hotkey/HotkeyManager.swift:191`<br>Both handle tapDisabledByTimeout. | `equivalent` | None. Same behavior. |
| **KEY-6** Esc cancels the active session | `GlobalShortcut.swift:124`<br>`AppModel.swift:114` | `Settings/HotkeySettingsView.swift:141`<br>`App/HotkeyLifecycle.swift:235`<br>Voxt has a toggle. The default is on. | `equivalent` | None. Same behavior. |
| **KEY-7** One shortcut runs the selected mode; mode picker on Home | `Views.swift:194`<br>`OmniTyperApp.swift:46-73` | `Settings/HotkeySettingsView.swift:590`<br>Voxt binds one hotkey to each mode: transcription, translation and rewrite. | `equivalent` | None. Separate hotkeys give the same mode choice. |

## Audio capture and recording panel

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **AUD-1** Microphone selection | `AudioRecorder.swift:130`<br>`AudioRecorder.swift:160`<br>`PreferencesView.swift:29` | `Core/AudioInputDeviceManager.swift:17`<br>`Core/MicrophonePreferenceManager.swift:119`<br>`App/MenuWindowCoordinator.swift:121`<br>Voxt adds a priority list and auto switch. OmniTyper fails the session on a device change (AudioRecorder.swift:198). | `equivalent` | None. Voxt is a superset. |
| **AUD-2** Input level meter | `AudioRecorder.swift:13-106`<br>`Views.swift:282` | `Core/AudioLevelMeter.swift`<br>`Windows/WaveformView.swift`<br>Voxt draws a waveform. | `equivalent` | None. Same purpose. |
| **AUD-3** Start and stop sounds | `AppModel.swift:214`<br>`AppModel.swift:223`<br>`PreferencesView.swift:33` | `Core/InteractionSoundPlayer.swift:30`<br>`Core/InteractionSoundPlayer.swift:51`<br>`Settings/Shell/AppPreferenceKey.swift:74-75`<br>Voxt has sound presets. | `equivalent` | None. Voxt is a superset. |
| **AUD-4** 5-minute recording limit with auto finish | `AppModel.swift:80`<br>`backend/worker.py:168` | `sglang_omni_mlx/qwen3_asr/server.py:195`<br>Voxt has no dictation cap. The Voxt Omni server splits audio with --max-segment-seconds (default 30). | `obsolete` | None. The cap matched server.py --audio_chunking.max_total_audio_s 300. That server is not used by Voxt. |
| **AUD-5** Non-activating floating panel with live text | `OmniTyperApp.swift:94-107`<br>`Views.swift:282` | `Windows/RecordingOverlayWindow.swift:30-35`<br>`Settings/GeneralSettingsView.swift:22`<br>Both panels do not take focus. Voxt live text has an on/off toggle. | `equivalent` | None. Same behavior. |
| **AUD-6** Panel shows elapsed time and Stop and Cancel buttons | `Views.swift:282` | None found<br>No button or elapsed-time view found in Windows/RecordingOverlay*.swift or Windows/Waveform*.swift (searched Button(, elapsed, duration). | `gap` | **Drop.** The hotkey stops the session and Esc cancels it. Mouse controls add little. |
| **AUD-7** Silence gate returns no text | `backend/worker.py:196` | `App/Recording/RecordingTextRouting.swift:81`<br>`Transcription/MLXTranscriber.swift:469`<br>Voxt uses local VAD. OmniTyper uses an energy threshold. | `equivalent` | None. Same purpose. |
| **AUD-8** Live transcript preview over /v1/realtime | `ASRStream.swift:5-122`<br>`Views.swift:224` | `Transcription/OmniRealtimeTranscriptionSession.swift:81`<br>`Transcription/MLXTranscriber.swift:1117`<br>Voxt Omni preview updates once per second (Voxt/backend/README.md). | `equivalent` | None. Same feature. |

## Speech recognition backend

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **ASR-1** Local speech server on loopback with a random port | `backend/server.py:65-145` | `Voxt/backend/voxt_omni_backend/supervisor.py:35`<br>`Voxt/backend/voxt_omni_backend/supervisor.py:39`<br>`Transcription/OmniASRRuntime.swift:250`<br>OmniTyper runs sglang_omni.cli serve with SGLANG_USE_MLX=1. Voxt runs sglang_omni_mlx.qwen3_asr.server without torch or SGLang. | `equivalent` | None. Same role. |
| **ASR-2** Omni backend in a normal build (no environment variables) | `scripts/setup.sh:7-14`<br>`scripts/build.sh:7-34`<br>`PreferencesView.swift:66`<br>`WorkerClient.swift:314` | `Transcription/OmniASRBackend.swift:36-44`<br>`Voxt/backend/run_omni_dev.sh`<br>Voxt enables Omni only in the Voxt Omni Dev build. It needs VOXT_ASR_BACKEND=omni, VOXT_OMNI_PYTHON and VOXT_OMNI_BACKEND_DIR. | `partial` | **Fill (L).** Resolve the Python runtime and backend directory without environment variables. Show the Omni engine in model settings. |
| **ASR-3** Model mlx-community/Qwen3-ASR-0.6B-4bit at a pinned revision | `backend/server.py:24-26` | `Transcription/OmniASRBackend.swift:26-28`<br>`Transcription/MLXModelDownloadSupport.swift:243`<br>Voxt downloads resolve/main. OmniTyper pins revision 313d850181767edf09f00a9c289becca70e58cd0. | `partial` | **Fill (S).** Pin the revision for the Omni repo in MLXModelDownloadSupport.swift:243. |
| **ASR-4** Use the cached model without network access | `backend/server.py:29-55` | `Transcription/MLXModelManager.swift:835-847`<br>Voxt starts the Omni runtime from its installed model directory. | `equivalent` | None. Same behavior. |
| **ASR-5** Prepare ASR and Unload ASR buttons | `PreferencesView.swift:61-62`<br>`AppModel.swift:372`<br>`AppModel.swift:416` | `App/Recording/RecordingCaptureFlow.swift:58`<br>`Settings/Shell/AppPreferenceKey.swift:131-133`<br>Voxt prewarms at session start and unloads after an idle delay of 10-1200 s. It has no manual buttons. | `partial` | **Drop.** Prewarm and idle unload replace the manual buttons. Row PR-2250-C covers keep-loaded. |
| **ASR-6** Cancel keeps the model loaded; Unload stops the server process group | `AppModel.swift:418`<br>`backend/server.py:205-225` | `Transcription/MLXModelManager.swift:844`<br>`Voxt/backend/voxt_omni_backend/supervisor.py`<br>Voxt stops earlier runtimes before it starts a new one. | `equivalent` | None. Same purpose. |
| **ASR-7** Readiness wait and preparation progress | `backend/server.py:65-145`<br>`Views.swift:144`<br>`WorkerClient.swift:221` | `Voxt/backend/voxt_omni_backend/supervisor.py:254`<br>`Settings/Models/ModelDownloadStatusView.swift:12-40`<br>The supervisor polls /health and /v1/models. | `equivalent` | None. Same purpose. |
| **ASR-8** Dictionary hints in the final transcription prompt | `backend/server.py:147-203` | `Transcription/OmniASRRuntime.swift:411`<br>`Core/Transcription/ASRHintLocalTuning.swift:486`<br>OmniTyper sends the first 20 written forms. Voxt fills {{DICTIONARY_TERMS}}. | `equivalent` | None. Same feature. |
| **ASR-9** Speech language selection | `PreferencesView.swift:41`<br>`ASRStream.swift:84` | `Core/Transcription/ASRHintResolver.swift:34`<br>`Transcription/MLXInferenceConfiguration.swift:50`<br>Voxt takes the language from the user main languages (userMainLanguageCodes). | `equivalent` | None. Same purpose. |
| **ASR-10** Full-file final pass after streaming | `backend/worker.py:254`<br>`AppModel.swift:278-290` | `Transcription/MLXTranscriber.swift:1692`<br>`Transcription/OmniASRRuntime.swift:212`<br>Both send the full WAV to /v1/audio/transcriptions. | `equivalent` | None. Same behavior. |
| **ASR-11** Remote sglang-omni server | `ASRStream.swift:52`<br>`backend/server.py:65-145` | `Transcription/RemoteASR/RemoteASRFileRequests.swift:9-13`<br>`Transcription/RemoteASR/RemoteASRTextSupport.swift:49-67`<br>`Core/RemoteProviders/RemoteEndpointSecurityPolicy.swift:45-47`<br>`Transcription/RemoteASR/RemoteASRTranscriber.swift:264`<br>`Voxt/docs/RemoteModel.md:7-35`<br>OmniTyper is local only. Voxt OpenAI Whisper provider can call a remote /v1/audio/transcriptions. It needs a non-empty API key. Plain HTTP with a key works only on loopback. No /v1/realtime streaming. | `partial` | **Fill (S).** Make the API key optional for custom endpoints in RemoteASRFileRequests.swift:11-13. sglang-omni inference endpoints need no key. |

## Text API (LLM)

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **LLM-1** OpenAI-compatible text API, default Ollama | `Store.swift:26-55`<br>`backend/text_api.py:97` | `Core/Models/RemoteModelConfiguration.swift:343`<br>`Voxt/docs/RemoteModel.md`<br>Voxt has 17 LLM providers, Ollama included. | `equivalent` | None. Voxt is a superset. |
| **LLM-2** Fetch the model list and choose a model | `PreferencesView.swift:74-98`<br>`AppModel.swift:391`<br>`backend/worker.py:228` | `Core/RemoteProviders/RemoteConnectivityTester.swift:38`<br>Voxt uses preset model lists, a custom model ID and a Test button. No live GET /models list found. | `partial` | **Drop.** A custom model ID and the connectivity Test cover setup. |
| **LLM-3** API key kept in memory only | `AppModel.swift:24` | `Core/Security/VoxtSecureStorage.swift:143`<br>Voxt stores the key in the Keychain. The ad-hoc Omni Dev build may not keep it (Voxt/backend/README.md:97). | `partial` | **Drop.** The Keychain is the macOS store for secrets. The user does not re-enter the key after each launch. |
| **LLM-4** Request options JSON | `Store.swift:26-55`<br>`PreferencesView.swift:98` | `Settings/RemoteProviderSheetSections.swift:541`<br>Voxt calls it Extra Body JSON. | `equivalent` | None. Same feature. |
| **LLM-5** Endpoint checks: URL validation, no redirects, 1 MiB response limit | `backend/text_api.py:97` | `Core/RemoteProviders/RemoteEndpointSecurityPolicy.swift:30-47`<br>Voxt validates the URL and blocks credentials over plain HTTP to remote hosts. No redirect block or response size limit found. | `partial` | **Drop.** The credential rule covers the main risk. Response limits are general hardening, not a migration item. |
| **LLM-6** Output guards: think stripping, tool-call rejection, finish_reason length is an error | `backend/text_api.py:161-199` | `Core/LLM/LLMVisibleOutputSanitizer.swift:78-83`<br>Voxt strips <think>. No check for finish_reason length or tool calls found in Core/LLM. | `partial` | **Fill (S).** Treat finish_reason length as a failure in Core/LLM/RemoteLLMStreamingParser.swift. A cut-off cleanup must not reach the cursor. |
| **LLM-7** Per-task prompt templates with escaping and examples | `backend/text_api.py:19-53` | `Core/FeaturePromptPreset.swift:128-140`<br>`Resources/Prompts/en/en-enhancement.txt`<br>`Resources/Prompts/en/en-rewrite.txt`<br>Voxt prompts are user-editable. | `equivalent` | None. Same purpose. |

## Dictionary

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **DIC-1** Preferred spellings as recognition hints | `Store.swift:97`<br>`backend/server.py:147-203` | `Core/Dictionary/DictionaryModels.swift:139`<br>Voxt adds categories and match counts. | `equivalent` | None. Voxt is a superset. |
| **DIC-2** Literal replacements: longest first, case-insensitive, word boundary | `backend/worker.py:201` | `Core/Dictionary/DictionaryMatchingSupport.swift:314`<br>`Core/Dictionary/DictionaryMatchingSupport.swift:385-394`<br>Voxt replacement terms always apply. | `equivalent` | None. Same purpose. |
| **DIC-3** CSV import and export | `Store.swift:307`<br>`Store.swift:320`<br>`LibraryViews.swift:98` | `Core/Dictionary/DictionaryTransferManager.swift:9`<br>`Core/Dictionary/DictionaryTransferManager.swift:110`<br>`Core/Dictionary/DictionaryTransferManager.swift:136`<br>Voxt imports and exports JSON only. | `partial` | **Fill (S).** Add CSV to DictionaryTransferManager. This also moves an exported OmniTyper dictionary into Voxt. |
| **DIC-4** Learn a word from a history correction | `LibraryViews.swift:73`<br>`Store.swift:291` | `Core/Dictionary/DictionaryLearningMonitor.swift`<br>`Settings/Shell/AppPreferenceKey.swift:181`<br>Voxt learns from edits to delivered text and from history scans. It has no manual correction editor. | `partial` | **Drop.** Auto learning and manual dictionary entry cover the need. |
| **DIC-5** Entry validation and limits | `Store.swift:97`<br>`Store.swift:291` | `Core/Dictionary/EntryValidationSupport.swift`<br>Limits differ. OmniTyper allows 200 entries of 120 characters. | `equivalent` | None. Same purpose. |

## Writing style

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **STY-1** Style presets: verbatim, clean, casual, formal, concise | `backend/text_api.py:26-32`<br>`Views.swift:15` | `Core/FeaturePromptPreset.swift:128-140`<br>Voxt has Precise Cleanup and Clear Structure. Verbatim equals enhancement off. No casual, formal or concise preset. | `partial` | **Fill (S).** Add Casual, Formal and Concise presets in FeaturePromptPreset.swift. |
| **STY-2** Global custom instructions | `LibraryViews.swift:161` | `Settings/Features/FeatureSettings.swift:270`<br>Voxt uses an editable prompt. | `equivalent` | None. Same purpose. |
| **STY-3** Per-app style rule | `LibraryViews.swift:161`<br>`AppModel.swift:238` | `Settings/AppEnhancement/AppEnhancementModels.swift:40-50`<br>Voxt groups apps and URL patterns. | `equivalent` | None. Voxt is a superset. |

## Text insertion

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **INS-1** Paste at cursor, then restore the full clipboard | `TextInsertion.swift:134-179` | `App/TextOutputDelivery.swift:54-113`<br>`App/TextOutputDelivery.swift:215`<br>`Core/Utilities/PasteboardTextWriter.swift:18-54`<br>Voxt restores only the previous text. Images, files and rich text on the clipboard are lost. | `partial` | **Fill (S).** Snapshot and restore all pasteboard item types in PasteboardTextWriter. |
| **INS-2** Transient and concealed pasteboard markers | `TextInsertion.swift:157`<br>`TextInsertion.swift:212` | None found<br>Searched org.nspasteboard, TransientType and ConcealedType. No match. Clipboard managers record every Voxt result. | `gap` | **Fill (S).** Set org.nspasteboard.TransientType and ConcealedType in PasteboardTextWriter. |
| **INS-3** Block secure fields and secure input | `TextInsertion.swift:85`<br>`TextInsertion.swift:246`<br>`AppModel.swift:166` | None found<br>Searched SecureEventInput, IsSecureEventInputEnabled, AXSecureTextField and AXProtectedContent. No match. | `gap` | **Fill (S).** Check IsSecureEventInputEnabled() and the AXSecureTextField subrole before start and before paste in TextOutputDelivery. |
| **INS-4** Direct AXSelectedText write in native apps | `TextInsertion.swift:123-131` | `App/TextOutputDelivery.swift:215`<br>Voxt always pastes with Cmd+V. | `gap` | **Drop.** Paste works in all apps. With INS-1 and INS-2 filled, paste has no clipboard cost. |
| **INS-5** Validate that the same editable field still has focus | `TextInsertion.swift:26-44`<br>`TextInsertion.swift:97` | `App/TextOutputDelivery.swift:19-52`<br>`App/TextInjectionTransaction.swift`<br>Voxt re-activates the session app only. It does not check the field. | `partial` | **Drop.** Voxt pastes at the current focus by design. History keeps every result. |
| **INS-6** No editable field or no Accessibility: copy instead | `TextInsertion.swift:97`<br>`TextInsertion.swift:106-108`<br>`AppModel.swift:317` | `Settings/Shell/AppPreferenceKey.swift:111`<br>`App/TextOutputDelivery.swift:54-113`<br>Voxt uses autoCopyWhenNoFocusedInput. OmniTyper also writes a note into the history entry. | `equivalent` | None. Same purpose. |
| **INS-7** Detect an ignored paste and fall back | `TextInsertion.swift:183-196` | `App/TextOutputDelivery.swift:206`<br>Searched pasteWasIgnored. AXNumberOfCharacters appears only in App/TextInputIO.swift:254 for snapshots. | `gap` | **Drop.** History keeps the result. The custom paste hotkey re-pastes it (TextOutputDelivery.swift:206). The detection is a heuristic. |
| **INS-8** Enable Accessibility in Chromium and Electron apps | `TextInsertion.swift:54-71` | None found<br>Searched AXManualAccessibility and AXEnhancedUserInterface. No match. | `gap` | **Drop.** Voxt does not need field detection to paste. Selection reads use AppleScript and Cmd+C fallbacks (App/SelectedTextProbe.swift:30). |
| **INS-9** Auto paste off: copy only | `Store.swift:57-95`<br>`PreferencesView.swift:34` | None found<br>Searched paste and clipboard keys in AppPreferenceKey.swift. Only autoCopyWhenNoFocusedInput and the custom paste hotkey exist. | `gap` | **Drop.** No request for copy-only output. autoCopyWhenNoFocusedInput covers the no-field case. |

## History and local data

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **HIS-1** History list with search and mode filter | `LibraryViews.swift:14` | `Settings/History/HistorySettingsView.swift:34`<br>`Settings/History/HistorySettingsView.swift:314`<br>`Settings/History/HistorySettingsComponents.swift:12-17`<br>Voxt filters by transcription, translation, rewrite, note and transcript. | `equivalent` | None. Same feature. |
| **HIS-2** Copy, delete one, delete all | `LibraryViews.swift:26-27`<br>`LibraryViews.swift:49`<br>`LibraryViews.swift:56` | `Settings/History/HistorySettingsComponents.swift:117`<br>`Settings/History/HistorySettingsComponents.swift:139`<br>`Settings/History/HistorySettingsView.swift:684`<br>`Core/History/TranscriptionHistoryStore.swift:402`<br>Voxt deletes all entries of one kind. | `equivalent` | None. Same feature. |
| **HIS-3** Original transcript next to the processed text | `LibraryViews.swift:59`<br>`Views.swift:234-249` | `Core/History/TranscriptionHistoryModels.swift:71-111`<br>Voxt stores the final text and dictionary correction snapshots. It does not store the transcript before LLM cleanup. | `partial` | **Fill (M).** Add an optional raw transcript field to TranscriptionHistoryEntry. Show it in the history detail sheet. |
| **HIS-4** Export history as JSON | `LibraryViews.swift:26`<br>`LibraryViews.swift:226` | None found<br>Searched exportJSON, export.*History and NSSavePanel in Core/History and Settings/History. Only audio export exists. | `gap` | **Drop.** No migration flow depends on it. Meeting export and audio export cover the main data. |
| **HIS-5** History on/off and retention | `Store.swift:265`<br>`PreferencesView.swift:104-115` | `Settings/Shell/AppPreferenceKey.swift:123-126`<br>Voxt has retention by period and by count. | `equivalent` | None. Voxt is a superset. |
| **HIS-6** Keep audio (off by default) and export WAV | `Store.swift:217`<br>`LibraryViews.swift:54`<br>`LibraryViews.swift:226` | `Settings/Shell/AppPreferenceKey.swift:127`<br>`Core/History/HistoryAudioArchiveService.swift:17`<br>`Core/History/HistoryAudioArchiveSupport.swift:10`<br>Voxt exports all archives at once. | `equivalent` | None. Same feature. |
| **HIS-7** Retry from saved audio and retry last | `AppModel.swift:347`<br>`AppModel.swift:356`<br>`LibraryViews.swift:53`<br>`Views.swift:51-56` | None found<br>Searched retranscribe, retryTranscription, transcribeHistoryAudio and reprocessHistory. No history retry found. | `gap` | **Fill (M).** Add Transcribe Again to history entries with audio. Reuse the final-pass path in MLXTranscriber. |
| **HIS-8** Usage stats | `Views.swift:250-254` | `Settings/ReportSettingsView.swift:42-63`<br>Voxt has a dashboard with time, characters and speed. | `equivalent` | None. Voxt is a superset. |
| **HIS-9** Local data store; a corrupt file is not overwritten | `Store.swift:148`<br>`Store.swift:185-189`<br>`Store.swift:205` | `Core/History/HistoryRepository.swift`<br>`Core/Dictionary/DictionaryRepository.swift`<br>Voxt keeps history and dictionary in repositories. File mode 0600 was not checked. | `equivalent` | None. Same purpose. |
| **HIS-10** Import OmniTyper data (library.json and Audio/) | `Store.swift:148` | None found<br>Searched OmniTyper and library.json in Voxt/. No match. | `gap` | **Drop.** OmniTyper is a development demo. DIC-3 moves the dictionary. Old files stay on disk. |
| **HIS-11** Migrate from OpenTypeless | `Store.swift:170-176` | None found<br>OpenTypeless is the earlier OmniTyper name. | `obsolete` | None. No Voxt user has OpenTypeless data. |
| **HIS-12** Open the data folder | `PreferencesView.swift:104-115` | None found<br>Searched activateFileViewerSelecting, selectFile, Show in Finder and Open Folder in Settings. No match. | `gap` | **Drop.** The Logs sheet exports logs. The user picks the audio folder (AppPreferenceKey.swift:128). |

## App shell, settings and localization

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **APP-1** Menu bar app; closing the window keeps it running | `Resources/Info.plist`<br>`OmniTyperApp.swift:19`<br>`OmniTyperApp.swift:89-90` | `Settings/Shell/AppPreferenceKey.swift:122`<br>`App/MenuWindowCoordinator.swift:93`<br>Voxt has a Show in Dock toggle. | `equivalent` | None. Same behavior. |
| **APP-2** Start, stop and cancel without a shortcut (menu items and Home button) | `OmniTyperApp.swift:46-73`<br>`Views.swift:198-204` | `App/MenuWindowCoordinator.swift:93-158`<br>The Voxt menu has Dashboard, History, Dictionary, Microphone and Quit. It has no start, stop or cancel item. | `partial` | **Drop.** Hotkeys start every Voxt session. Onboarding teaches the hotkey. |
| **APP-3** Appearance: light, dark or system | `Views.swift:73`<br>`PreferencesView.swift:123` | `Settings/Shell/SettingsUIStyles.swift:211`<br>Voxt follows the system appearance only. | `partial` | **Drop.** The macOS appearance setting covers it. |
| **APP-4** Interface language with runtime switch | `Localization.swift:17`<br>`PreferencesView.swift:47` | `Settings/Shell/SettingsTypes.swift:22-26`<br>`Core/Utilities/AppLocalization.swift:30`<br>Voxt adds Japanese. | `equivalent` | None. Voxt is a superset. |
| **APP-5** Open at login | `PreferencesView.swift:124` | `Core/AppBehaviorController.swift:42`<br>Both use SMAppService. | `equivalent` | None. Same feature. |
| **APP-6** Launch arguments --background and --snapshot | `OmniTyperApp.swift:38-43`<br>`OmniTyperApp.swift:109` | None found<br>--snapshot renders README screenshots. --background starts hidden. | `obsolete` | None. Development helpers for the OmniTyper package only. |
| **APP-7** macOS 14 support | `Package.swift`<br>`Resources/Info.plist` | `Voxt/Voxt.xcodeproj/project.pbxproj:475`<br>Voxt requires macOS 15.0. OmniTyper requires macOS 14.0. | `partial` | **Drop.** Voxt upstream targets macOS 15. A lower target is an app-wide port. |

## Permissions and diagnostics

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **PRM-1** Microphone and Accessibility checks with settings links | `AppModel.swift:126-144`<br>`PreferencesView.swift:131-132`<br>`Views.swift:169-182` | `Settings/PermissionsSettingsView.swift`<br>`Settings/Onboarding/OnboardingGuidePermissions.swift`<br>`Core/Security/AccessibilityPermissionManager.swift`<br>Voxt adds an onboarding guide. | `equivalent` | None. Voxt is a superset. |
| **PRM-2** Detect a stale Accessibility grant after a rebuild | `AppModel.swift:126-144`<br>`Store.swift:57-95` | None found<br>Searched stale, tccutil and re-add guidance in permission code. No match. Config/OmniDev.xcconfig:18 signs ad hoc, so each rebuild loses the grant. | `gap` | **Fill (S).** Store a was-trusted flag in AccessibilityPermissionManager. Show remove-and-re-add guidance when the flag is set and trust is gone. |
| **PRM-3** Bounded diagnostics log without user content | `Diagnostics.swift:5-49` | `Core/Logging/VoxtLogFileStore.swift:12`<br>`Core/Logging/VoxtLog.swift:78-82`<br>`Settings/LogsViewerSheet.swift:85`<br>Voxt rotates the log file, redacts secrets and keeps LLM content out of files. | `equivalent` | None. Voxt is a superset. |
| **PRM-4** Microphone usage text and audio-input entitlement | `Resources/Info.plist:17`<br>`Resources/Entitlements.plist` | `Voxt/Voxt.xcodeproj/project.pbxproj:563`<br>`VoxtOmniDev.entitlements`<br>None. | `equivalent` | None. Same feature. |

## Build, packaging and tests

| Feature | OmniTyper (file:line) | Voxt equivalent (file:line) | Status | Recommendation |
| --- | --- | --- | --- | --- |
| **DEV-1** setup.sh: arm64 check, dependencies, build | `scripts/setup.sh:7-14`<br>`backend/requirements.txt` | `Voxt/backend/setup_env.sh`<br>Voxt installs a uv venv from requirements-mac.lock. | `obsolete` | None. Voxt has its own setup script. |
| **DEV-2** build.sh: app bundle, icon, hardened-runtime signing | `scripts/build.sh:7-34`<br>`scripts/icon.swift` | `Voxt/backend/run_omni_dev.sh`<br>`Voxt/tools/package_local_app.sh`<br>Voxt builds with Xcode. | `obsolete` | None. Voxt has its own build. |
| **DEV-3** Sign with a chosen identity so TCC grants survive rebuilds | `scripts/build.sh:7-34` | `Voxt/Config/OmniDev.xcconfig:18`<br>`Voxt/Config/Signing.local.xcconfig.example:5-6`<br>OmniTyper reads $CODE_SIGN_IDENTITY. OmniDev.xcconfig forces ad-hoc signing (CODE_SIGN_IDENTITY = -). | `partial` | **Fill (S).** Let OmniDev.xcconfig take VOXT_CODE_SIGN_IDENTITY from Signing.local.xcconfig when it exists. |
| **DEV-4** Python JSON-lines worker and WorkerClient | `backend/worker.py:306`<br>`WorkerClient.swift:47-314` | `Transcription/OmniASRRuntime.swift`<br>Voxt calls the server over HTTP. Text API calls run in Swift. | `obsolete` | None. The worker protocol has no role in Voxt. |
| **DEV-5** Python runtime path setting and relocation | `PreferencesView.swift:66`<br>`Store.swift:193-200`<br>`WorkerClient.swift:314` | `Transcription/OmniASRBackend.swift:36-44`<br>Voxt reads VOXT_OMNI_PYTHON. | `obsolete` | None. Row ASR-2 covers the user-facing need. |
| **DEV-6** Unit tests (Swift and Python) | `Tests/OmniTyperTests`<br>`backend/test_worker.py`<br>`scripts/test.sh:13-14` | `Voxt/VoxtTests/OmniASRRuntimeLaunchTests.swift`<br>`Voxt/VoxtTests/OmniFailurePathTests.swift`<br>`Voxt/VoxtTests/OmniPhase1LifecycleTests.swift`<br>`Voxt/VoxtTests/OmniTranscriptionRequestTests.swift`<br>`Voxt/backend/tests/test_supervisor.py`<br>Neither runs in sglang-omni CI. Voxt/.github/workflows/tests.yml is nested, so GitHub does not run it. | `equivalent` | None. Same coverage role. |
| **DEV-7** Real-model smoke tests and realtime fixture | `backend/smoke.py`<br>`backend/smoke_stream.py`<br>`Tests/realtime_server.py` | `Voxt/VoxtTests/OmniPhase1BenchmarkTests.swift`<br>`Voxt/backend/tests/fake_omni_server.py`<br>The smoke tests drive the OmniTyper worker protocol. | `obsolete` | None. Voxt has its own fake server and benchmark tests. |
| **DEV-8** README: setup, data paths, troubleshooting | `README.md:62-76` | `Voxt/backend/README.md`<br>The README describes OmniTyper only. | `obsolete` | None. Voxt/backend/README.md documents the Omni build. |

## Unmerged OmniTyper PRs

All PRs below are open. A PR with several features has one row per feature. sgl-project/sglang-omni#2434 also changes server code under `sglang_omni/`.

| PR | Title | Feature | Voxt equivalent | Status | Recommendation |
| --- | --- | --- | --- | --- | --- |
| sgl-project/sglang-omni#2240 | [Fix] OmniTyper: correct Swift requirements and icon types | **PR-2240** Swift tools 6.0 check and icon CGFloat types | None found<br>Voxt builds with Xcode. | `obsolete` | None. The fix applies to the OmniTyper package only. |
| sgl-project/sglang-omni#2241 | [Feature] OmniTyper: configurable Hugging Face endpoint and mirror download UX | **PR-2241** Hugging Face endpoint setting and Use hf-mirror.com and retry | `Transcription/MLXModelManager.swift:1089-1101`<br>Voxt probes huggingface.co and hf-mirror.com and picks a reachable source. No custom endpoint field. | `partial` | **Drop.** The automatic probe covers the mirror case. |
| sgl-project/sglang-omni#2394 | feat(omnityper): support Hugging Face mirrors for ASR | **PR-2394** Optional Hugging Face endpoint; invalid endpoint stops Prepare | `Transcription/MLXModelManager.swift:1089-1101`<br>Same as PR-2241. It fixes sgl-project/sglang-omni#2239. | `partial` | **Drop.** The automatic probe covers sgl-project/sglang-omni#2239. |
| sgl-project/sglang-omni#2242 | [Fix] OmniTyper: preserve permissions, report shortcut conflicts, add ModelScope | **PR-2242-A** Stable local signing identity (sign.sh, test-signing.sh) | `Voxt/Config/OmniDev.xcconfig:18`<br>Same as DEV-3. | `partial` | **Fill (S).** Same fill as DEV-3. |
| sgl-project/sglang-omni#2242 | [Fix] OmniTyper: preserve permissions, report shortcut conflicts, add ModelScope | **PR-2242-B** Pause the shortcut while a new one is captured | `Hotkey/HotkeyCaptureState.swift:13-30`<br>Voxt sets hotkeyCaptureInProgress. | `equivalent` | None. Same behavior. |
| sgl-project/sglang-omni#2242 | [Fix] OmniTyper: preserve permissions, report shortcut conflicts, add ModelScope | **PR-2242-C** Conflict messages: system, registered hotkeys, listener failure | `Settings/HotkeySettingsValidation.swift:14-24`<br>`Hotkey/HotkeyRecorderView.swift:184`<br>Voxt checks a static list of system shortcuts. No query of registered hotkeys found. | `partial` | **Drop.** The static list covers the common system shortcuts. |
| sgl-project/sglang-omni#2242 | [Fix] OmniTyper: preserve permissions, report shortcut conflicts, add ModelScope | **PR-2242-D** ModelScope download source | None found<br>Searched modelscope and ModelScope in Voxt/. No match. | `gap` | **Drop.** The hf-mirror.com probe covers mainland China access. |
| sgl-project/sglang-omni#2250 | [OmniTyper] Improve window controls and everyday usability | **PR-2250-A** Window polish: title bar, draggable popup, larger click targets | `Settings/Shell/AppPreferenceKey.swift:77-80`<br>Voxt has its own UI. The overlay position is top or bottom and does not drag. | `obsolete` | None. The changes target OmniTyper views only. |
| sgl-project/sglang-omni#2250 | [OmniTyper] Improve window controls and everyday usability | **PR-2250-B** Key names, Fn combinations, F1-F20 | `Hotkey/HotkeySupport.swift:430`<br>`Hotkey/HotkeyPreferencePresentation.swift:44-53`<br>Voxt supports Fn. The key name table has no F1-F20 entries. | `partial` | **Fill (S).** Add F1-F20 names in HotkeyPreferencePresentation.swift. |
| sgl-project/sglang-omni#2250 | [OmniTyper] Improve window controls and everyday usability | **PR-2250-C** Keep the speech model loaded | `Settings/Shell/AppPreferenceKey.swift:131-133`<br>The Voxt idle unload delay has a 1200 s maximum. | `partial` | **Fill (S).** Add a Never option to the idle unload delay. The Omni server cold start is slow. |
| sgl-project/sglang-omni#2251 | [OmniTyper] Redesign mode selection and popup interaction | **PR-2251-A** Hold the shortcut and move to pick a mode | None found<br>Voxt binds one hotkey to each mode. | `gap` | **Drop.** Separate hotkeys give direct mode access. |
| sgl-project/sglang-omni#2251 | [OmniTyper] Redesign mode selection and popup interaction | **PR-2251-B** Review panel with pause, resume, Insert, Copy and Clear | `Windows/WaveformAnswerCard.swift:128`<br>`Windows/WaveformAnswerCard.swift:151`<br>`Meeting/MeetingSessionModels.swift`<br>Voxt answer cards have Inject and Copy. Pause exists only in Meeting Notes. | `partial` | **Drop.** The answer card covers review. Meeting Notes covers long pausable capture. |
| sgl-project/sglang-omni#2251 | [OmniTyper] Redesign mode selection and popup interaction | **PR-2251-C** Voice edit of the whole text box when nothing is selected | `Voxt/docs/Rewrite.md`<br>Voxt Rewrite without a selection writes new text from the prompt. | `gap` | **Drop.** Select-all before Rewrite gives the same result. |
| sgl-project/sglang-omni#2251 | [OmniTyper] Redesign mode selection and popup interaction | **PR-2251-D** Ask single-turn answer view | `Windows/WaveformAnswerCard.swift:124`<br>Voxt adds Continue for follow-up turns. | `equivalent` | None. Voxt is a superset. |
| sgl-project/sglang-omni#2256 | [Feature] OmniTyper: show speech model download progress and status | **PR-2256** Download percentage and model status (missing, downloaded, loaded) | `Settings/Models/ModelDownloadStatusView.swift:12-40`<br>Voxt shows download progress and install state. | `equivalent` | None. Same feature. |
| sgl-project/sglang-omni#2303 | [Feature] OmniTyper: optional compact waveform capsule as the recording popup | **PR-2303** Compact waveform capsule popup | `Windows/WaveformView.swift`<br>`Settings/GeneralSettingsView.swift:22`<br>The Voxt overlay is a waveform capsule. Live text off keeps it compact. Click to finish is not in Voxt. | `equivalent` | None. Same presentation. |
| sgl-project/sglang-omni#2304 | [Fix] OmniTyper: keep the popup responsive while the microphone starts and stops | **PR-2304** Start and stop the audio engine off the main actor | `Transcription/MLXTranscriber.swift:883-891`<br>Voxt starts the engine in a detached task with a timeout. | `equivalent` | None. Same fix. |
| sgl-project/sglang-omni#2434 | [ASR] Forward vocabulary hints through realtime transcription | **PR-2434** Dictionary hints in realtime session.update prompt | `Transcription/OmniRealtimeTranscriptionSession.swift:212-218`<br>`sglang_omni_mlx/qwen3_asr/realtime.py`<br>Voxt sends language only in session.update. The MLX realtime server reads no prompt. The final pass has hints (ASR-8). | `gap` | **Fill (M).** Keep the server part of this PR. Add prompt to Voxt session.update and to sglang_omni_mlx realtime. |
| sgl-project/sglang-omni#2523 | [Feature] OmniTyper: meeting notetaker | **PR-2523** Meeting notetaker: 3 h recording, chunked transcription, Markdown summary | `Voxt/docs/Meeting.md`<br>`Transcription/MLXTranscriber.swift:975-979`<br>`Core/TranscriptSummarySupport.swift:213`<br>Voxt Meeting Notes runs on the Omni runtime and has summaries and export. It labels Me and Them. | `equivalent` | None. Voxt is a superset. |

## Sources

- OmniTyper source: last commit that changes `OmniTyper/` is `c4a0145472be6d5c1a566ccc0963fbf462a37bff` (sgl-project/sglang-omni#2519).
- Worktree HEAD for all refs: `abba158ef8f88ed987c0045ccacd6186e1cfe38b`.
- Voxt import: hehehai/voxt at `baa6f316` (`Voxt/PROVENANCE.md`).
- No file outside `OmniTyper/` refers to OmniTyper (`git grep -i omnityper`).
- PR data: `gh pr view` and `gh pr diff` for each PR in this document.

Merged OmniTyper PRs:

| PR | Title | Rows |
| --- | --- | --- |
| sgl-project/sglang-omni#2214 | [Feature] Add OmniTyper with MLX streaming ASR and configurable text APIs | All main rows |
| sgl-project/sglang-omni#2231 | [Fix] OmniTyper: remove the Settings main-thread stall, dictate without a text API, add Simplified Chinese | MOD-1, APP-4 |
| sgl-project/sglang-omni#2237 | [Fix] OmniTyper: record lone modifier shortcuts such as Fn | KEY-3 |
| sgl-project/sglang-omni#2255 | [Fix] OmniTyper: stop reporting successful terminal pastes as ignored | INS-7 |
| sgl-project/sglang-omni#2261 | [Fix] OmniTyper: withdraw the unkept copy promise, show preparation progress in Settings, point at where verbatim is set, stop Unload ASR orphaning the speech server | ASR-5, ASR-6, ASR-7, STY-1 |
| sgl-project/sglang-omni#2275 | [Deps] Bump SGLang to 0.5.20 | DEV-1 |
| sgl-project/sglang-omni#2505 | [Deps] Bump SGLang to 0.5.21 | DEV-1 |
| sgl-project/sglang-omni#2519 | [Fix] OmniTyper: limit Esc cancellation, keep the model loaded on cancel, clipboard history, notices | KEY-6, ASR-6, INS-2 |

Closed without merge: sgl-project/sglang-omni#2247 and sgl-project/sglang-omni#2249. sgl-project/sglang-omni#2250 replaces them.
