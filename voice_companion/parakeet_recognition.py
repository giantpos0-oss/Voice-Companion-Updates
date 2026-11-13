"""Offline utterance recognition. Vosk remains the lightweight wake detector."""
from pathlib import Path


class ParakeetRecognition:
    def __init__(self, model_folder: Path):
        import onnx_asr
        if not model_folder.is_dir() or not any(model_folder.iterdir()):
            raise FileNotFoundError('Bundled Parakeet model is missing')
        self.model = onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v3',
                                         str(model_folder), quantization='int8')

    def recognize(self, pcm: bytes) -> str:
        import numpy as np
        samples = np.frombuffer(pcm, dtype='<i2').astype(np.float32) / 32768.0
        if len(samples) < 1600:
            return ''
        return str(self.model.recognize(samples, sample_rate=16000)).strip()


FRAME_SAMPLES = 320          # 20 ms at 16,000 samples a second
PAD_SECONDS = 0.3            # kept before and after the speech, so no word is clipped
MIN_LEVEL = 300              # quieter than this (out of 32,768) is never speech


def speech_span(pcm: bytes, rate: int = 16000) -> bytes:
    """The part of a recording that has speech in it, with a little room each side.

    Parakeet takes longer the more sound it is given. The recording reaches back to
    the end of the last words, so it starts with silence, and it ends with the pause
    that marked the end of speaking (Will, November 12, 2026: dictation should come
    back faster). Returns b'' when there is no speech at all. Room noise sets the bar:
    a frame counts as speech when it is clearly louder than the quiet parts."""
    import numpy as np
    samples = np.frombuffer(pcm[:len(pcm) - len(pcm) % 2], dtype='<i2').astype(np.float32)
    frames = len(samples) // FRAME_SAMPLES
    if frames == 0:
        return b''
    levels = np.sqrt(np.mean(samples[:frames * FRAME_SAMPLES].reshape(frames, FRAME_SAMPLES) ** 2, axis=1))
    floor = float(np.percentile(levels, 20))
    # Clearly above the room noise; capped by the loudest moment, so speech with no pause still counts.
    loud = np.nonzero(levels >= max(MIN_LEVEL, min(floor * 3, float(levels.max()) * 0.3)))[0]
    if len(loud) == 0:
        return b''
    pad = int(PAD_SECONDS * rate / FRAME_SAMPLES)
    first = max(0, int(loud[0]) - pad)
    last = min(frames, int(loud[-1]) + 1 + pad)
    end = len(samples) if last == frames else last * FRAME_SAMPLES
    return pcm[first * FRAME_SAMPLES * 2:end * 2]
