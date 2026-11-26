import pytest

from pipeline.compose import build_command, compose
from pipeline.fakes import FakeTtsBackend, FakeVideoGenerator


def make_media(ffmpeg, tmp_path, clip_seconds, voice_seconds):
    """按给定的秒数造出镜头片段和旁白音频。"""
    clips = [
        FakeVideoGenerator(ffmpeg, seconds=seconds).generate_video(tmp_path / "none.png", "运镜", 1, tmp_path, f"shot_{index:03d}")
        for index, seconds in enumerate(clip_seconds, start=1)
    ]
    voices = [
        FakeTtsBackend(seconds=seconds).synthesize("旁白", tmp_path, f"voice_{index:03d}")
        for index, seconds in enumerate(voice_seconds, start=1)
    ]
    return clips, voices


def test_compose_aligns_every_shot_to_five_seconds(ffmpeg, tmp_path):
    clips, voices = make_media(ffmpeg, tmp_path, clip_seconds=[5.5, 2], voice_seconds=[5, 1])
    out = tmp_path / "final.mp4"

    assert compose(clips, voices, out, ffmpeg, width=128, height=224) == out

    assert abs(ffmpeg.duration(out) - 10.0) < 0.1
    assert "128x224" in ffmpeg.run(["-loglevel", "info", "-i", str(out), "-map", "0", "-f", "null", "-"])


def test_compose_rejects_mismatched_counts(ffmpeg, tmp_path):
    clips, voices = make_media(ffmpeg, tmp_path, clip_seconds=[5, 5], voice_seconds=[5])

    with pytest.raises(ValueError, match="数量必须一致"):
        compose(clips, voices, tmp_path / "final.mp4", ffmpeg, width=128, height=224)


def test_compose_rejects_empty_input(ffmpeg, tmp_path):
    with pytest.raises(ValueError, match="没有镜头可以合成"):
        compose([], [], tmp_path / "final.mp4", ffmpeg)


def test_build_command_rejects_odd_dimensions(tmp_path):
    with pytest.raises(ValueError, match="偶数"):
        build_command([tmp_path / "a.mp4"], [tmp_path / "a.wav"], tmp_path / "out.mp4", 5.0, 24, 127, 224)


def test_build_command_labels_streams_in_order(tmp_path):
    command = build_command(
        [tmp_path / "a.mp4", tmp_path / "b.mp4"],
        [tmp_path / "a.wav", tmp_path / "b.wav"],
        tmp_path / "out.mp4",
        5.0,
        24,
        128,
        224,
    )

    filters = command[command.index("-filter_complex") + 1].split(";")
    assert filters[0].startswith("[0:v]fps=24,scale=128:224")
    assert filters[1].startswith("[1:v]fps=24")
    assert filters[2].startswith("[2:a]aresample=44100")
    assert filters[3].startswith("[3:a]aresample=44100")
    assert filters[4] == "[v0][v1]concat=n=2:v=1:a=0[vout]"
    assert filters[5] == "[a0][a1]concat=n=2:v=0:a=1[aout]"
    assert command[-1] == str(tmp_path / "out.mp4")
