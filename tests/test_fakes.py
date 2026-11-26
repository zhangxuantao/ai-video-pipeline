import soundfile as sf
from PIL import Image

from pipeline.episode import validate_episode
from pipeline.fakes import FakeImageGenerator, FakeTtsBackend, FakeVideoGenerator, fake_episode


def test_fake_episode_passes_validation_for_any_shot_count():
    validate_episode(fake_episode("青丘山的九尾狐", "e1", 1))
    validate_episode(fake_episode("青丘山的九尾狐", "e2", 24))


def test_fake_image_is_a_real_png(tmp_path):
    path = FakeImageGenerator().generate_image("画面", 1, tmp_path, "keyframe_001")

    with Image.open(path) as image:
        assert (image.format, image.size) == ("PNG", (64, 64))


def test_fake_video_has_requested_duration(ffmpeg, tmp_path):
    path = FakeVideoGenerator(ffmpeg, seconds=2).generate_video(tmp_path / "none.png", "运镜", 1, tmp_path, "shot_001")

    assert abs(ffmpeg.duration(path) - 2.0) < 0.1


def test_fake_voice_has_requested_duration(tmp_path):
    path = FakeTtsBackend(seconds=3).synthesize("旁白", tmp_path, "voice_001")

    data, sample_rate = sf.read(path)
    assert sample_rate == 24000
    assert abs(len(data) / sample_rate - 3.0) < 0.01
