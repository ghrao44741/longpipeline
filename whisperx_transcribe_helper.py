"""
_whisperx_transcribe_helper.py — run inside the transcription venv only.

Transcribes+force-aligns an audio file with WhisperX and writes word-level
timestamps as JSON. Invoked as a subprocess by verify_output.py's
check_caption_sync(), which runs in a different Python environment that has
openai-whisper/pydub/PIL but not whisperx (GPU-dependent, lives in
C:/Bakcup_Asus/shared-tools/transcription-tools/.venv). Kept as a tiny,
single-purpose script rather than inline subprocess -c text to avoid escaping
a multi-line script through two layers of shell quoting.

Usage:
    <transcription_venv_python> _whisperx_transcribe_helper.py <audio_path> <output_json_path> [device]
"""
import json
import sys

audio_path, output_path = sys.argv[1], sys.argv[2]
device = sys.argv[3] if len(sys.argv) > 3 else "cuda"

import whisperx  # noqa: E402

model = whisperx.load_model("base", device, compute_type="float16" if device == "cuda" else "float32")
audio = whisperx.load_audio(audio_path)
result = model.transcribe(audio, batch_size=4)
model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
result = whisperx.align(result["segments"], model_a, metadata, audio, device)

words = []
for seg in result["segments"]:
    for w in seg.get("words", []):
        if "start" in w:
            words.append({"word": w["word"], "start": float(w["start"])})

with open(output_path, "w", encoding="utf-8") as f:
    json.dump({"words": words}, f)

print(f"wrote {len(words)} words to {output_path}")
