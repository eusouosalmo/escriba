"""Transcreve o áudio de uma pasta usando o Qwen3-ASR servido pelo llama.cpp.

Duas escolhas moldam este script, e ambas vieram de medição, não de gosto:

O áudio é cortado nos silêncios e não em blocos de tamanho fixo, para que
nenhuma frase seja partida ao meio — um corte no meio de uma palavra degrada o
reconhecimento dos dois lados dele.

O modelo é servido por um `llama-server` que sobe uma vez, em vez de invocar a
CLI por chunk. A CLI recarrega o modelo a cada chamada, e com dezenas de chunks
a carga passaria a dominar o tempo total.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _contract import ENVIRONMENT, FAILED, USAGE, fail, log, succeed

LLAMA_SERVER = Path.home() / ".local/opt/llama.cpp/llama-server"

# Espaço que cada modelo precisa na GPU, com a folga que os testes mostraram
# ser necessária: o pico é dominado pelo encoder de áudio, não pelos pesos.
MODELS = [
    ("ggml-org/Qwen3-ASR-1.7B-GGUF:Q8_0", "Qwen3-ASR-1.7B", "Q8_0", 3100),
    ("ggml-org/Qwen3-ASR-0.6B-GGUF:Q8_0", "Qwen3-ASR-0.6B", "Q8_0", 1900),
]

SILENCE_NOISE_DB = -30
SILENCE_MIN_DURATION = 0.35

DEFAULT_TARGET = 30.0
DEFAULT_MAXIMUM = 120.0

PROMPT = "Transcribe the audio."
ASR_PATTERN = re.compile(r"<asr_text>(.*?)(?:</asr_text>|$)", re.DOTALL)
LANGUAGE_PATTERN = re.compile(r"language\s+(\w+)")


@dataclass
class Chunk:
    start: float
    end: float
    text: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


# ---------------------------------------------------------------- ambiente


def free_vram_mib() -> int | None:
    """Mede a VRAM livre agora, porque ela não é a da placa.

    Num notebook o Windows consome de 750 MiB a 2 GB da GPU conforme o que
    estiver aberto, então o orçamento real muda entre uma execução e outra.
    """
    if not shutil.which("nvidia-smi"):
        return None
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        total, used = (int(x) for x in result.stdout.strip().splitlines()[0].split(","))
    except (ValueError, IndexError):
        return None
    return total - used


def choose_model(free_mib: int | None, requested: str | None = None) -> tuple[str, str, str]:
    """Escolhe o maior modelo que cabe no que há de VRAM livre.

    Sem GPU visível, assume o menor: rodar devagar é melhor que não rodar.
    """
    if requested:
        for repo, name, quant, _ in MODELS:
            if requested in (name, repo) or requested in name.lower():
                return repo, name, quant
        fail(
            f"modelo {requested!r} não é conhecido",
            code=USAGE,
            hint=f"use um destes: {', '.join(name for _, name, _, _ in MODELS)}",
        )

    if free_mib is None:
        return MODELS[-1][:3]

    for repo, name, quant, needed in MODELS:
        if free_mib >= needed:
            return repo, name, quant
    return MODELS[-1][:3]


# ------------------------------------------------------------------- vad


def detect_silences(audio: Path) -> list[tuple[float, float]]:
    result = subprocess.run(
        [
            "ffmpeg", "-v", "info", "-i", str(audio),
            "-af", f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={SILENCE_MIN_DURATION}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", result.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", result.stderr)]
    return list(zip(starts, ends, strict=False))


def audio_duration(audio: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        fail(f"não foi possível medir a duração de {audio.name}", code=FAILED)


def plan_chunks(
    duration: float,
    silences: list[tuple[float, float]],
    target: float = DEFAULT_TARGET,
    maximum: float = DEFAULT_MAXIMUM,
) -> list[Chunk]:
    """Transforma silêncios em fronteiras de chunk.

    O corte cai no meio do silêncio, que é o ponto mais seguro: longe da última
    palavra de um lado e da primeira do outro. Acumula trechos até passar do
    alvo; só quando não há silêncio algum por tempo demais é que corta no seco,
    o que acontece em trilha sonora contínua.
    """
    boundaries = [(start + end) / 2 for start, end in silences if 0 < start < duration]

    chunks: list[Chunk] = []
    position = 0.0
    for boundary in boundaries:
        if boundary - position < target:
            continue
        while boundary - position > maximum:
            chunks.append(Chunk(position, position + maximum))
            position += maximum
        chunks.append(Chunk(position, boundary))
        position = boundary

    while duration - position > maximum:
        chunks.append(Chunk(position, position + maximum))
        position += maximum
    if duration - position > 0.1:
        chunks.append(Chunk(position, duration))

    return chunks


def slice_audio(audio: Path, chunk: Chunk, destination: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(audio),
            "-ss", f"{chunk.start:.3f}", "-to", f"{chunk.end:.3f}",
            "-c", "copy", str(destination), "-y",
        ],
        capture_output=True,
        check=True,
    )


# ---------------------------------------------------------------- servidor


class Server:
    """Sobe o llama-server e garante que ele morra junto com o script.

    Um servidor órfão segura a GPU inteira, e numa placa de 4 GB isso inviabiliza
    a próxima execução — por isso o encerramento vive num `finally` e não no
    caminho feliz.
    """

    def __init__(self, repo: str, port: int) -> None:
        self.repo = repo
        self.port = port
        self.process: subprocess.Popen | None = None

    def start(self, timeout: float = 900.0) -> None:
        if not LLAMA_SERVER.exists():
            fail(
                f"llama-server não encontrado em {LLAMA_SERVER}",
                code=ENVIRONMENT,
                hint="instale o llama.cpp em ~/.local/opt/llama.cpp",
            )

        log(f"subindo o servidor com {self.repo}...")
        self.process = subprocess.Popen(
            [
                str(LLAMA_SERVER), "-hf", self.repo,
                "--port", str(self.port), "--no-warmup", "-c", "8192",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={**os.environ, "LD_LIBRARY_PATH": str(LLAMA_SERVER.parent)},
        )

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                fail(
                    "o servidor encerrou antes de ficar pronto",
                    code=FAILED,
                    hint="verifique se há VRAM livre suficiente",
                )
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=2):
                    log("servidor pronto")
                    return
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(2)

        fail("o servidor não ficou pronto a tempo", code=FAILED)

    def transcribe(self, audio: Path, timeout: float = 600.0) -> str:
        encoded = base64.b64encode(audio.read_bytes()).decode()
        payload = json.dumps(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_audio", "input_audio": {"data": encoded, "format": "wav"}},
                            {"type": "text", "text": PROMPT},
                        ],
                    }
                ],
                "max_tokens": 2048,
                "temperature": 0,
            }
        ).encode()

        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
        return body["choices"][0]["message"]["content"]

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)


# ------------------------------------------------------------ pós-processo


def clean(raw: str) -> tuple[str, str | None]:
    """Extrai o texto da resposta e remove o que o modelo repetiu sem motivo.

    Modelos de ASR entram em laço quando o áudio é ambíguo — música, ruído, um
    trecho sem fala — e repetem a mesma frase muitas vezes. Deixar isso passar
    contamina a transcrição inteira com texto que ninguém falou.
    """
    language_match = LANGUAGE_PATTERN.search(raw)
    language = language_match.group(1) if language_match else None

    match = ASR_PATTERN.search(raw)
    text = match.group(1) if match else LANGUAGE_PATTERN.sub("", raw)
    return collapse_repetitions(text.strip()), language


def collapse_repetitions(text: str, threshold: int = 3) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        normalized = sentence.strip().lower()
        if not normalized:
            continue
        repeats = sum(1 for previous in kept[-threshold:] if previous.strip().lower() == normalized)
        if repeats >= 1 and len(kept) >= threshold:
            recent = [p.strip().lower() for p in kept[-threshold:]]
            if recent.count(normalized) >= threshold - 1:
                continue
        kept.append(sentence.strip())
    return " ".join(kept)


# --------------------------------------------------------------- formatos


def to_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def write_outputs(folder: Path, chunks: list[Chunk], language: str | None, meta: dict) -> None:
    populated = [c for c in chunks if c.text]

    (folder / "transcript.txt").write_text(
        "\n\n".join(f"[{to_timestamp(c.start)[:-4]}] {c.text}" for c in populated) + "\n",
        encoding="utf-8",
    )

    entries = []
    for index, chunk in enumerate(populated, start=1):
        entries.append(
            f"{index}\n{to_timestamp(chunk.start)} --> {to_timestamp(chunk.end)}\n{chunk.text}\n"
        )
    (folder / "transcript.srt").write_text("\n".join(entries), encoding="utf-8")

    (folder / "transcript.json").write_text(
        json.dumps(
            {
                "language": language,
                "text": " ".join(c.text for c in populated),
                "segments": [
                    {"start": round(c.start, 3), "end": round(c.end, 3), "text": c.text}
                    for c in populated
                ],
                **meta,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def update_metadata(folder: Path, meta: dict) -> None:
    path = folder / "metadata.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log("aviso: metadata.json ausente ou ilegível — seguindo sem atualizá-lo")
        return
    data.update(meta)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ main


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcreve o áudio de uma pasta")
    parser.add_argument("folder", help="pasta do vídeo, com audio.wav dentro")
    parser.add_argument("--model", help="força um modelo em vez de escolher pela VRAM livre")
    parser.add_argument(
        "--target", type=float, default=DEFAULT_TARGET,
        help=f"duração alvo de cada chunk em segundos (padrão: {DEFAULT_TARGET:g})",
    )
    parser.add_argument(
        "--maximum", type=float, default=DEFAULT_MAXIMUM,
        help=f"duração máxima antes de cortar no seco (padrão: {DEFAULT_MAXIMUM:g})",
    )
    parser.add_argument("--port", type=int, default=18080, help="porta do servidor")
    parser.add_argument("--force", action="store_true", help="transcreve de novo se já existir")
    args = parser.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            fail(f"{tool} não foi encontrado", code=ENVIRONMENT, hint="instale o ffmpeg")

    folder = Path(args.folder)
    audio = folder / "audio.wav"
    if not audio.is_file():
        fail(
            f"não há audio.wav em {folder}",
            code=USAGE,
            hint="rode a extração de áudio antes da transcrição",
            folder=str(folder),
        )

    transcript = folder / "transcript.txt"
    if transcript.exists() and not args.force:
        log(f"transcrição já existe em {transcript}")
        succeed(folder=str(folder), transcript=str(transcript), reused=True)

    free = free_vram_mib()
    repo, model_name, quantization = choose_model(free, args.model)
    log(f"VRAM livre: {free if free is not None else 'desconhecida'} MiB — usando {model_name}")

    duration = audio_duration(audio)
    silences = detect_silences(audio)
    chunks = plan_chunks(duration, silences, args.target, args.maximum)
    log(f"{duration:.0f}s de áudio em {len(chunks)} chunks (mediana alvo {args.target:g}s)")

    workdir = folder / ".chunks"
    workdir.mkdir(exist_ok=True)

    server = Server(repo, args.port)
    language: str | None = None
    started = time.monotonic()
    try:
        server.start()
        for index, chunk in enumerate(chunks, start=1):
            piece = workdir / f"{index:04d}.wav"
            slice_audio(audio, chunk, piece)
            try:
                raw = server.transcribe(piece)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                fail(
                    f"o servidor falhou no chunk {index} de {len(chunks)}",
                    code=FAILED,
                    details=str(error)[:300],
                    folder=str(folder),
                )
            chunk.text, detected = clean(raw)
            language = language or detected
            piece.unlink(missing_ok=True)
            log(f"chunk {index}/{len(chunks)} ({chunk.duration:.0f}s)")
    finally:
        server.stop()
        shutil.rmtree(workdir, ignore_errors=True)

    elapsed = time.monotonic() - started
    meta = {
        "transcription_engine": "qwen3-asr/llama.cpp",
        "transcription_model": model_name,
        "transcription_quantization": quantization,
        "transcription_chunk_target_seconds": args.target,
        "transcription_chunk_maximum_seconds": args.maximum,
        "transcription_chunks": len(chunks),
        "transcription_language": language,
        "transcription_seconds": round(elapsed, 1),
    }
    write_outputs(folder, chunks, language, meta)
    update_metadata(folder, meta)

    log(f"pronto em {elapsed:.0f}s ({duration / elapsed:.1f}x tempo real)")
    succeed(
        folder=str(folder),
        transcript=str(transcript),
        srt=str(folder / "transcript.srt"),
        json=str(folder / "transcript.json"),
        model=model_name,
        language=language,
        chunks=len(chunks),
        seconds=round(elapsed, 1),
        reused=False,
    )


if __name__ == "__main__":
    main()
