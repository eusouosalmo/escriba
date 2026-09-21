"""Testes da extração de áudio.

O ffmpeg é exercitado de verdade, com clipes minúsculos gerados na hora — são
rápidos o bastante para caber num teste e provam o que importa: que o formato
entregue é o que o reconhecimento de fala espera, e que um vídeo mudo produz
uma explicação em vez de um erro de stream.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import extract_audio

SCRIPT = ROOT / "scripts" / "extract_audio.py"


def make_clip(path: Path, *, silent: bool = False, seconds: int = 1) -> Path:
    command = ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s=160x120:d={seconds}"]
    if not silent:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    command += ["-c:v", "libx264", "-shortest", str(path), "-y"]
    subprocess.run(command, check=True, capture_output=True)
    return path


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


@pytest.fixture
def folder_with_video(tmp_path: Path) -> Path:
    make_clip(tmp_path / "video.mp4")
    (tmp_path / "metadata.json").write_text(
        json.dumps({"title": "clipe de teste"}), encoding="utf-8"
    )
    return tmp_path


def test_produces_audio_in_the_format_the_asr_expects(folder_with_video: Path):
    result = run(str(folder_with_video))

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["sample_rate"] == 16_000
    assert payload["channels"] == 1

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_name,sample_rate,channels",
            "-of", "json", str(folder_with_video / "audio.wav"),
        ],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["codec_name"] == "pcm_s16le"
    assert stream["sample_rate"] == "16000"
    assert stream["channels"] == 1


def test_records_what_it_generated_without_losing_what_was_there(folder_with_video: Path):
    run(str(folder_with_video))

    metadata = json.loads((folder_with_video / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "clipe de teste"
    assert metadata["audio_file"] == "audio.wav"
    assert metadata["audio_sample_rate"] == 16_000


def test_second_run_reuses_instead_of_extracting_again(folder_with_video: Path):
    run(str(folder_with_video))
    before = (folder_with_video / "audio.wav").stat().st_mtime_ns

    payload = json.loads(run(str(folder_with_video)).stdout)

    assert payload["reused"] is True
    assert (folder_with_video / "audio.wav").stat().st_mtime_ns == before


def test_force_extracts_again(folder_with_video: Path):
    run(str(folder_with_video))

    payload = json.loads(run(str(folder_with_video), "--force").stdout)

    assert payload["reused"] is False


def test_a_silent_video_is_explained_not_dumped_as_an_ffmpeg_error(tmp_path: Path):
    make_clip(tmp_path / "video.mp4", silent=True)

    result = run(str(tmp_path))

    assert result.returncode == extract_audio.FAILED
    payload = json.loads(result.stdout)
    assert "não tem faixa de áudio" in payload["error"]
    assert "transcrever" in payload["hint"]
    assert not (tmp_path / "audio.wav").exists()


def test_a_folder_without_video_is_a_usage_error(tmp_path: Path):
    result = run(str(tmp_path))

    assert result.returncode == extract_audio.USAGE
    assert "rode o download antes" in json.loads(result.stdout)["hint"]


def test_a_missing_folder_is_a_usage_error(tmp_path: Path):
    result = run(str(tmp_path / "nao-existe"))

    assert result.returncode == extract_audio.USAGE


def test_missing_metadata_does_not_fail_the_extraction(tmp_path: Path):
    """O áudio no disco é o resultado; metadata ausente é contratempo, não falha."""
    make_clip(tmp_path / "video.mp4")

    result = run(str(tmp_path))

    assert result.returncode == 0
    assert (tmp_path / "audio.wav").exists()
