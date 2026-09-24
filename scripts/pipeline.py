"""Encadeia as três etapas: baixar, extrair o áudio, transcrever.

Não há máquina de estados aqui, e isso é de propósito. Cada etapa já reconhece
o próprio trabalho feito e devolve `reused: true` em vez de refazê-lo, então
retomar uma execução interrompida é apenas rodar tudo de novo: o que já existe
responde em segundos e só o que falta é executado.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _contract import ENVIRONMENT, FAILED, fail, log, succeed

SCRIPTS = Path(__file__).resolve().parent

STAGES = [
    ("download", "download.py"),
    ("extração de áudio", "extract_audio.py"),
    ("transcrição", "transcribe.py"),
]


def run_stage(script: str, arguments: list[str]) -> tuple[dict, int]:
    """Roda uma etapa e devolve o que ela respondeu, junto com o exit code.

    stdout é o canal de dados e stderr passa adiante sem filtro, para que o
    progresso da etapa continue visível a quem chamou o pipeline.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stderr:
        sys.stderr.write(result.stderr)
        sys.stderr.flush()

    try:
        return json.loads(result.stdout), result.returncode
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": f"{script} não devolveu um resultado legível",
            "details": (result.stdout or result.stderr).strip()[:300],
        }, result.returncode or FAILED


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa, extrai o áudio e transcreve")
    parser.add_argument("url", help="URL do vídeo")
    parser.add_argument("--output-dir", default="downloads")
    parser.add_argument("--model", help="força um modelo de transcrição")
    parser.add_argument("--target", type=float, help="duração alvo dos blocos, em segundos")
    parser.add_argument("--max-height", type=int, help="altura máxima do vídeo em pixels")
    parser.add_argument("--force", action="store_true", help="refaz todas as etapas")
    args = parser.parse_args()

    started = time.monotonic()

    def fail_stage(label: str, payload: dict, code: int) -> None:
        # O código e a dica da etapa são preservados: ela sabe melhor que o
        # pipeline o que aconteceu, e reinterpretar aqui só perderia informação.
        fail(
            payload.get("error", f"a etapa de {label} falhou"),
            code=code or FAILED,
            hint=payload.get("hint"),
            stage=label,
            **{k: v for k, v in payload.items() if k not in {"ok", "error", "hint"}},
        )

    log("[1/3] download")
    arguments = [args.url, "--output-dir", args.output_dir]
    if args.max_height is not None:
        arguments += ["--max-height", str(args.max_height)]
    if args.force:
        arguments.append("--force")

    download, code = run_stage("download.py", arguments)
    if code != 0 or not download.get("ok"):
        fail_stage("download", download, code)

    # Um post pode trazer vários vídeos. Cada um segue o mesmo caminho, e o
    # caso de um só é apenas a lista de tamanho um.
    videos = download.get("items") or [download]
    processed: list[dict] = []
    reused_any = False

    skipped: list[dict] = []

    def handle(label: str, payload: dict, code: int, folder: str) -> bool:
        """Decide se uma falha derruba tudo ou apenas descarta este vídeo.

        Num post com vários vídeos, um item mudo ou defeituoso não pode
        inviabilizar os outros — descartá-lo e seguir preserva o trabalho já
        feito. Falha de ambiente é exceção: ela vai se repetir em todos, e
        insistir só produziria a mesma mensagem sete vezes.
        """
        if code == 0 and payload.get("ok"):
            return True
        if len(videos) == 1 or code == ENVIRONMENT:
            fail_stage(label, payload, code)
        log(f"aviso: pulando {folder} — {payload.get('error')}")
        skipped.append(
            {"folder": folder, "stage": label, "error": payload.get("error")}
        )
        return False

    for number, item in enumerate(videos, start=1):
        prefix = f" ({number}/{len(videos)})" if len(videos) > 1 else ""
        folder = item["folder"]

        log(f"[2/3] extração de áudio{prefix}")
        extract_arguments = [folder] + (["--force"] if args.force else [])
        extracted, code = run_stage("extract_audio.py", extract_arguments)
        if not handle("extração de áudio", extracted, code, folder):
            continue

        log(f"[3/3] transcrição{prefix}")
        transcribe_arguments = [folder]
        if args.model:
            transcribe_arguments += ["--model", args.model]
        if args.target is not None:
            transcribe_arguments += ["--target", str(args.target)]
        if args.force:
            transcribe_arguments.append("--force")
        transcribed, code = run_stage("transcribe.py", transcribe_arguments)
        if not handle("transcrição", transcribed, code, folder):
            continue

        reused_any = reused_any or all(
            step.get("reused") for step in (item, extracted, transcribed)
        )
        processed.append(
            {
                "folder": folder,
                "title": item.get("title"),
                "duration": item.get("duration"),
                "video": item.get("video"),
                "audio": extracted.get("audio"),
                "transcript": transcribed.get("transcript"),
                "srt": transcribed.get("srt"),
                "json": transcribed.get("json"),
                "language": transcribed.get("language"),
                "model": transcribed.get("model"),
                "speech": transcribed.get("speech"),
            }
        )

    elapsed = time.monotonic() - started

    if not processed:
        fail(
            "nenhum dos vídeos do post pôde ser transcrito",
            code=FAILED,
            skipped=skipped,
        )

    silent = [item for item in processed if item.get("speech") is False]
    if silent:
        log(f"{len(silent)} de {len(processed)} vídeo(s) não tinham fala reconhecível")
    if skipped:
        log(f"{len(skipped)} vídeo(s) descartado(s) de {len(videos)}")
    log(f"pipeline completo em {elapsed:.0f}s")

    first = processed[0]
    succeed(
        folder=first["folder"],
        title=first["title"],
        duration=first["duration"],
        video=first["video"],
        audio=first["audio"],
        transcript=first["transcript"],
        srt=first["srt"],
        json_file=first["json"],
        language=first["language"],
        model=first["model"],
        videos=processed if len(processed) > 1 else None,
        count=len(processed),
        without_speech=len(silent) or None,
        skipped=skipped or None,
        reused=reused_any,
        seconds=round(elapsed, 1),
    )


if __name__ == "__main__":
    main()
