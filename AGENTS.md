# AGENTS.md

Project instructions for coding agents working in this repository.

- Preserve the `ENABLE_AUDIO_SEPARATION` fallback: when it is `false`, the pipeline must use the original media audio for ASR, reference extraction, and final background mixing.
- Keep audio-separation and raw-audio temporary outputs isolated. The raw-audio mode uses `temp/<video>_rawaudio`; separated mode uses `temp/<video>`.
- Do not remove the Demucs `--two-stems vocals` contract unless the pipeline is updated to consume a different voice/background stem layout.
