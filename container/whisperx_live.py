"""Incremental GPU transcription of a WAV while pw-record is still writing it.

Uses the same faster-whisper engine and cached small model as WhisperX. A separate
process keeps inference away from Tk's event loop and releases VRAM on exit.
"""
import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel


def emit(kind, **data):
    print(json.dumps({"type": kind, **data}, ensure_ascii=False), flush=True)


def pcm_offset(path):
    with path.open("rb") as f:
        header = f.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            return None
        for _ in range(64):
            chunk = f.read(8)
            if len(chunk) < 8:
                return None
            name, length = struct.unpack("<4sI", chunk)
            if name == b"data":
                return f.tell()
            if length > 65536:
                return None
            f.seek(length + length % 2, 1)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--language", default="de")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # Cached by the normal WhisperX installation; no new model download needed.
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = WhisperModel("small", device=device, compute_type="int8", cpu_threads=4, local_files_only=True)
    emit("ready", message=f"Live-Modell auf {device} bereit.")
    rate, stride, context = 16000, 4 * 16000, 2 * 16000
    next_end, previous_end, committed_until = stride, 0, -1.0
    transcript = []
    selected_language = None if args.language == "auto" else args.language
    offset = None
    while offset is None:
        if args.audio.exists():
            offset = pcm_offset(args.audio)
        if offset is None:
            if args.stop_file.exists():
                raise RuntimeError("Die Aufnahme enthält keinen lesbaren WAV-Audiobereich.")
            time.sleep(.1)

    def process(end, final):
        nonlocal committed_until, selected_language
        start = max(0, previous_end - context)
        with args.audio.open("rb") as f:
            f.seek(offset + start * 2)
            raw = f.read((end - start) * 2)
        if not raw:
            return
        audio = np.frombuffer(raw[:len(raw) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
        if len(audio) < rate // 5 or np.max(np.abs(audio)) < .003:
            return
        segments, info = model.transcribe(audio, language=selected_language, beam_size=3, word_timestamps=True, vad_filter=True, vad_parameters={"min_silence_duration_ms": 350}, condition_on_previous_text=False, temperature=0)
        if selected_language is None and info.language_probability > .6:
            selected_language = info.language
        cutoff = end / rate if final else end / rate - .8
        for segment in segments:
            words = []
            for word in segment.words or []:
                word_start, word_end = start / rate + word.start, start / rate + word.end
                if (word_start + word_end) / 2 <= committed_until or word_end > cutoff:
                    continue
                words.append({"word": word.word, "start": word_start, "end": word_end})
                committed_until = max(committed_until, word_end - .04)
            if words:
                text = "".join(w["word"] for w in words).strip()
                item = {"start": words[0]["start"], "end": words[-1]["end"], "text": text, "words": words}
                transcript.append(item)
                (args.output / "live.txt").write_text("\n".join(s["text"] for s in transcript) + "\n")
                (args.output / "live.json").write_text(json.dumps({"language": selected_language, "segments": transcript, "preliminary": True}, ensure_ascii=False, indent=2))
                emit("partial", **item)

    while True:
        total = max(0, (args.audio.stat().st_size - offset) // 2)
        stopping = args.stop_file.exists()
        if total >= next_end:
            final = stopping and total == next_end
            process(next_end, final)
            previous_end = next_end
            next_end += stride
            if final:
                break
        elif stopping:
            # Revisit the final context to commit words held back at the boundary.
            process(total, True)
            break
        else:
            time.sleep(.15)
    if not transcript:
        (args.output / "live.txt").write_text("")
        (args.output / "live.json").write_text(json.dumps({"language": selected_language, "segments": [], "preliminary": True}))
    emit("finished", output_dir=str(args.output), text="\n".join(s["text"] for s in transcript))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("error", message=str(exc))
        sys.exit(1)
