import os
import shutil
import subprocess
import sys
from pathlib import Path

import pipeline.__main__ as entry
from pipeline.tts import TtsError

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflows"


def run_pipeline(cwd, *args, extra_env=None):
    """在指定目录下运行命令行入口，返回跑完的进程。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(extra_env or {})}
    return subprocess.run(
        [sys.executable, "-m", "pipeline", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )


def test_fakes_run_delivers_a_real_video(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", "--shot-count", "2", "--fakes")

    assert result.returncode == 0, result.stdout + result.stderr
    episode_id, status = result.stdout.strip().splitlines()[-1].split()
    assert status == "done"
    delivered = tmp_path / "data" / "deliver" / f"{episode_id}.mp4"
    assert delivered.is_file()
    assert delivered.stat().st_size > 1000


def test_run_fails_cleanly_without_api_key(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", extra_env={"DEEPSEEK_API_KEY": ""})

    assert result.returncode == 1
    assert "DEEPSEEK_API_KEY" in result.stderr


def test_check_workflows_accepts_fixture_workflows(tmp_path):
    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(FIXTURES)})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "seed -> 节点 3（KSampler）.seed" in result.stdout


def test_check_workflows_reports_broken_binding(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "wan_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "keyframe.binding.json").write_text('{"seed": ["99", "seed"]}', encoding="utf-8")

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 1
    assert "不存在的节点 99" in result.stderr


def test_check_workflows_reports_missing_required_binding(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "keyframe.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "wan_i2v.binding.json").write_text(
        '{"positive_prompt": ["6", "text"], "negative_prompt": ["7", "text"], "seed": ["3", "seed"], '
        '"width": ["5", "width"], "height": ["5", "height"], "length": ["5", "length"]}',
        encoding="utf-8",
    )

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 1
    assert "缺少必填参数 ['start_image']" in result.stderr


def test_check_workflows_lists_optional_params_that_are_not_bound(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "wan_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "keyframe.binding.json").write_text('{"positive_prompt": ["6", "text"]}', encoding="utf-8")

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 0
    assert "未绑定的可选参数" in result.stdout
    assert "negative_prompt" in result.stdout


def test_check_workflows_rejects_unknown_binding_keys(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "wan_i2v_api.json", "wan_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)
    (workflows / "keyframe.binding.json").write_text(
        '{"positive_prompt": ["6", "text"], "noise_seed": ["3", "seed"]}',
        encoding="utf-8",
    )

    result = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows)})

    assert result.returncode == 1
    assert "不认识的参数名 ['noise_seed']" in result.stderr


def test_check_workflows_requires_the_configured_engine(tmp_path):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    for name in ("keyframe_api.json", "keyframe.binding.json", "minimax_i2v_api.json", "minimax_i2v.binding.json"):
        shutil.copy(FIXTURES / name, workflows / name)

    missing = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows), "VIDEO_ENGINE": "wan"})
    ok = run_pipeline(tmp_path, "check-workflows", extra_env={"WORKFLOWS_DIR": str(workflows), "VIDEO_ENGINE": "minimax"})

    assert missing.returncode == 1
    assert "wan_i2v" in missing.stderr
    assert "必须提供" in missing.stderr
    assert ok.returncode == 0, ok.stdout + ok.stderr


def test_run_rejects_unknown_video_engine(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", "--fakes", extra_env={"VIDEO_ENGINE": "bogus"})

    assert result.returncode == 1
    assert "VIDEO_ENGINE 只能是" in result.stderr


def test_run_reports_setup_failure_without_traceback(tmp_path):
    result = run_pipeline(tmp_path, "run", "--topic", "青丘山的九尾狐", extra_env={"DEEPSEEK_API_KEY": "sk-test"})

    assert result.returncode == 1
    assert result.stdout.strip().endswith("failed")
    assert "读不到工作流文件" in result.stderr
    assert "Traceback" not in result.stderr


def test_tts_sample_reports_failure_in_chinese(tmp_path, monkeypatch, capsys):
    def broken_backend(*args, **kwargs):
        raise TtsError("没有这个音色")

    monkeypatch.setattr(entry, "KokoroTtsBackend", broken_backend)

    code = entry.main(["tts-sample", "--out", str(tmp_path / "sample.wav")])

    assert code == 1
    assert "配音示例失败" in capsys.readouterr().err
