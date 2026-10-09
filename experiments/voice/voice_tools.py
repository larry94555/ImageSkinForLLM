"""Candidate tools that speak in the person's voice, for the R25a voice cloning test.

- conversion: Kokoro speaks the text, then Chatterbox's voice converter (MIT) changes the timbre
  to the person's, learned from their voice sample. The timing does not change, so Kokoro's word
  and sound timings still drive the mouth. The accent is Kokoro's (American).
- clone: Chatterbox Turbo (MIT) speaks the text directly in a voice cloned from the sample,
  which keeps the person's own accent. It reports no word or sound timings. Larry picked it, so
  R25 moved it into the app (imageskin.chatterbox_engine), and this test now uses that copy;
  R26 moved the converter there too.

Both run on the CPU. Chatterbox marks its output with Resemble AI's inaudible Perth watermark.
The models (about 2 GB) are downloaded from Hugging Face on first use and cached.
"""

from collections.abc import Callable
from dataclasses import replace

import numpy as np

from imageskin.accent import (  # the app's conversion helpers (R26); this test reuses them
    convert_fitted,
    fit_length,
    pcm16_to_float,
)
from imageskin.chatterbox_engine import (  # the app's clone (R25) and converter (R26)
    SAMPLE_RATE,
    TurboCloner,
    TurboConverter,
    reference_clip,
)
from imageskin.kokoro_engine import to_pcm16
from imageskin.voice import Speech


def converted(speech: Speech, convert: Callable[[np.ndarray], np.ndarray]) -> Speech:
    """The same speech in another voice: new audio, the same word and sound timings."""
    out = convert_fitted(pcm16_to_float(speech.pcm), convert)
    return replace(speech, pcm=to_pcm16(out.tolist()))


# Chatterbox's converter with Turbo's one-step decoder, as the app runs it (R26).
ChatterboxConverter = TurboConverter
# Chatterbox Turbo cloning, as the app does it (`.tts` is the loaded model the converter shares).
ChatterboxCloner = TurboCloner
__all__ = [
    "SAMPLE_RATE",
    "ChatterboxCloner",
    "ChatterboxConverter",
    "converted",
    "fit_length",
    "pcm16_to_float",
    "reference_clip",
]
