"""Speech and per-sound timings from Kokoro (ONNX build, Apache 2.0) on the CPU.

kokoro-onnx's model files come from its GitHub release, not Hugging Face. The model is
patched in memory to also return how long it makes each phoneme, in 25 ms steps; the
steps add up exactly to the audio's length, so the timings line up with the voice.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "photoreal"))
from download import download  # noqa: E402

log = logging.getLogger("lipread.voice")

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_DIR = HERE / "models"
# Release files: (name, bytes, sha256).
KOKORO_SHA = "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"
VOICES_SHA = "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"
MODEL_FILES = [
    ("kokoro-v1.0.onnx", 325532387, KOKORO_SHA),
    ("voices-v1.0.bin", 28214398, VOICES_SHA),
]
DURATION_OUTPUT = "/encoder/Clip_output_0"  # rounded phoneme lengths inside the model
SAMPLE_RATE = 24000
SAMPLES_PER_STEP = 600  # one duration step is 25 ms


def split_sentences(text: str) -> list[str]:
    """Split on . ! ? so each sentence stays well under Kokoro's 510-phoneme limit."""
    out, cur = [], ""
    for ch in text:
        cur += ch
        if ch in ".!?":
            out.append(cur.strip())
            cur = ""
    if cur.strip():
        out.append(cur.strip())
    return [s for s in out if s]


def steps_to_seconds(steps: list[float]) -> list[float]:
    return [s * SAMPLES_PER_STEP / SAMPLE_RATE for s in steps]


class Voice:
    """Kokoro with a phoneme-duration output. Loads once, then speaks many sentences."""

    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        import numpy as np
        import onnx
        import onnxruntime
        from kokoro_onnx.tokenizer import Tokenizer

        start = time.perf_counter()
        for name, size, sha in MODEL_FILES:
            download(RELEASE + name, model_dir / name, size, sha)
        model = onnx.load(str(model_dir / "kokoro-v1.0.onnx"))
        model.graph.output.append(
            onnx.helper.make_tensor_value_info(DURATION_OUTPUT, onnx.TensorProto.FLOAT, None)
        )
        self.session = onnxruntime.InferenceSession(model.SerializeToString())
        self.voices: Any = np.load(str(model_dir / "voices-v1.0.bin"))
        self.tokenizer = Tokenizer()
        log.info("Kokoro loaded in %.1f s", time.perf_counter() - start)

    def speak(self, text: str, voice: str = "af_heart") -> tuple[Any, str, list[float]]:
        """Audio (float32, 24 kHz), the phonemes spoken and each phoneme's seconds.

        Each sentence starts and ends with a short silence (Kokoro's padding tokens), shown
        as "." in the phonemes so the mouth rests there.
        """
        import numpy as np

        start = time.perf_counter()
        audio, phonemes, seconds = [], "", []
        for sentence in split_sentences(text):
            ph = self.tokenizer.phonemize(sentence, "en-us")
            tokens = self.tokenizer.tokenize(ph)
            kept = "".join(ch for ch in ph if ch in self.tokenizer.vocab)
            if len(kept) != len(tokens):
                raise RuntimeError(f"Phoneme/token mismatch for {sentence!r}")
            style = self.voices[voice][len(tokens)]
            wav, steps = self.session.run(
                None,
                {
                    "tokens": [[0, *tokens, 0]],
                    "style": style,
                    "speed": np.ones(1, dtype=np.float32),
                },
            )
            phonemes += "." + kept + "."
            seconds += steps_to_seconds([float(s) for s in steps.ravel()])
            audio.append(wav.ravel().astype(np.float32))
            log.info("Spoke %r: %s", sentence, kept)
        out = np.concatenate(audio)
        log.info(
            "Speech ready: %.2f s of audio in %.2f s",
            len(out) / SAMPLE_RATE,
            time.perf_counter() - start,
        )
        return out, phonemes, seconds
