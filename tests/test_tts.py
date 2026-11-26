import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from pipeline.tts import KokoroTtsBackend, TtsError


class FakePipeline:
    """按调用参数返回固定音频块的 Kokoro 流水线替身。"""

    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def __call__(self, text, voice, speed):
        self.calls.append({"text": text, "voice": voice, "speed": speed})
        return [("文", "拼音", chunk) for chunk in self.chunks]


def test_synthesize_joins_chunks_into_one_wav(tmp_path):
    pipeline = FakePipeline([np.zeros(2400), np.full(2400, 0.5)])

    path = KokoroTtsBackend(voice="zm_yunxi", speed=1.1, pipeline_factory=lambda: pipeline).synthesize(
        "东海之外，有座青丘山。", tmp_path, "voice_001"
    )

    data, sample_rate = sf.read(path)
    assert path == tmp_path / "voice_001.wav"
    assert (sample_rate, len(data)) == (24000, 4800)
    assert data[2400] == pytest.approx(0.5, abs=1e-3)
    assert pipeline.calls == [{"text": "东海之外，有座青丘山。", "voice": "zm_yunxi", "speed": 1.1}]


def test_pipeline_is_built_once_and_reused(tmp_path):
    built = []
    pipeline = FakePipeline([np.zeros(2400)])
    backend = KokoroTtsBackend(pipeline_factory=lambda: built.append(1) or pipeline)

    backend.synthesize("第一句", tmp_path, "voice_001")
    backend.synthesize("第二句", tmp_path, "voice_002")

    assert built == [1]


def test_synthesize_fails_when_nothing_is_generated(tmp_path):
    backend = KokoroTtsBackend(pipeline_factory=lambda: FakePipeline([]))

    with pytest.raises(TtsError, match="没有合成出任何音频"):
        backend.synthesize("旁白", tmp_path, "voice_001")


def test_real_pipeline_uses_chinese_frontend_and_mirror(monkeypatch):
    created = {}

    def fake_pipeline(**options):
        created.update(options)
        return FakePipeline([np.zeros(2400)])

    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=fake_pipeline))
    backend = KokoroTtsBackend(hf_endpoint="https://hf-mirror.com")

    assert backend._build_pipeline() is not None

    assert created == {"lang_code": "z"}
    assert os.environ["HF_ENDPOINT"] == "https://hf-mirror.com"


@pytest.mark.integration
def test_real_kokoro_speaks_chinese(tmp_path):
    path = KokoroTtsBackend().synthesize("东海之外，有一座青丘山。", tmp_path, "voice_001")

    data, sample_rate = sf.read(path)
    assert len(data) / sample_rate > 1.0
