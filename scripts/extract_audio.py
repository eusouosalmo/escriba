"""Extrai do vídeo o áudio no formato que o reconhecimento de fala espera.

16 kHz, mono, PCM 16 bits não é escolha estética: é o que os modelos de ASR
consomem. Entregar qualquer outra coisa só empurra a conversão para a etapa
seguinte, que teria de fazer exatamente isto de novo.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _contract import ENVIRONMENT, FAILED, USAGE, fail, log, succeed

SAMPLE_RATE = 16_000
CHANNELS = 1
CODEC = "pcm_s16le"

VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        fail(
            f"{name} não foi encontrado",
            code=ENVIRONMENT,
            hint="instale o ffmpeg (no Ubuntu/Debian: `sudo apt install ffmpeg`)",
        )
    return path


def find_video(folder: Path) -> Path:
    if not folder.is_dir():
        fail(
            f"{folder} não é uma pasta existente",
            code=USAGE,
            hint="informe a pasta criada pelo download, como downloads/2020-05-24-titulo",
        )

    candidates = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in VIDEO_SUFFIXES)
    if not candidates:
        fail(
            f"nenhum vídeo encontrado em {folder}",
            code=USAGE,
            hint="rode o download antes da extração",
            folder=str(folder),
        )
    return candidates[0]


def probe_audio_stream(video: Path) -> dict | None:
    """Pergunta ao ffprobe se existe faixa de áudio, antes de tentar extrair.

    Sem essa checagem o ffmpeg falharia com uma mensagem técnica sobre mapas de
    stream, que não diz ao usuário a única coisa que importa: o vídeo é mudo.
    """
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,channels,duration",
            "-of",
            "json",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(
            f"não foi possível inspecionar {video.name}",
            code=FAILED,
            hint="o arquivo pode estar corrompido; tente baixar de novo com --force",
            details=result.stderr.strip()[:500],
        )

    streams = json.loads(result.stdout or "{}").get("streams") or []
    return streams[0] if streams else None


def duration_of(path: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return round(float(result.stdout.strip()), 3)
    except ValueError:
        return None


def extract(video: Path, destination: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video),
            "-vn",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            "-c:a",
            CODEC,
            str(destination),
            "-y",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        fail(
            f"o ffmpeg não conseguiu extrair o áudio de {video.name}",
            code=FAILED,
            details=result.stderr.strip()[:500],
        )


def update_metadata(folder: Path, audio: Path, duration: float | None) -> None:
    """Acrescenta o que foi gerado ao metadata.json, sem apagar o que já havia."""
    path = folder / "metadata.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # A extração pode rodar sobre uma pasta montada à mão. Não é motivo
        # para falhar: o áudio está no disco, que é o que importa.
        log("aviso: metadata.json ausente ou ilegível — seguindo sem atualizá-lo")
        return

    data["audio_file"] = audio.name
    data["audio_sample_rate"] = SAMPLE_RATE
    data["audio_channels"] = CHANNELS
    data["audio_duration_seconds"] = duration
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrai o áudio do vídeo de uma pasta")
    parser.add_argument("folder", help="pasta do vídeo, criada pelo download")
    parser.add_argument(
        "--force",
        action="store_true",
        help="extrai de novo mesmo que o áudio já exista",
    )
    args = parser.parse_args()

    require_tool("ffmpeg")
    require_tool("ffprobe")

    folder = Path(args.folder)
    video = find_video(folder)
    audio = folder / "audio.wav"

    if audio.exists() and not args.force:
        log(f"áudio já existe em {audio}")
        succeed(
            folder=str(folder),
            audio=str(audio),
            duration=duration_of(audio),
            sample_rate=SAMPLE_RATE,
            channels=CHANNELS,
            reused=True,
        )

    stream = probe_audio_stream(video)
    if stream is None:
        fail(
            f"{video.name} não tem faixa de áudio",
            code=FAILED,
            hint="não há o que transcrever neste vídeo",
            video=str(video),
        )

    log(f"extraindo áudio de {video.name}...")
    extract(video, audio)

    duration = duration_of(audio)
    update_metadata(folder, audio, duration)

    succeed(
        folder=str(folder),
        audio=str(audio),
        duration=duration,
        sample_rate=SAMPLE_RATE,
        channels=CHANNELS,
        reused=False,
    )


if __name__ == "__main__":
    main()
