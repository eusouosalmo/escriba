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

from _contract import FAILED, fail, log, succeed

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
    results: dict[str, dict] = {}

    for index, (label, script) in enumerate(STAGES, start=1):
        log(f"[{index}/{len(STAGES)}] {label}")

        if script == "download.py":
            arguments = [args.url, "--output-dir", args.output_dir]
            if args.max_height is not None:
                arguments += ["--max-height", str(args.max_height)]
        else:
            arguments = [results["download"]["folder"]]
            if script == "transcribe.py":
                if args.model:
                    arguments += ["--model", args.model]
                if args.target is not None:
                    arguments += ["--target", str(args.target)]

        if args.force:
            arguments.append("--force")

        payload, code = run_stage(script, arguments)

        if code != 0 or not payload.get("ok"):
            # O código e a dica da etapa são preservados: ela sabe melhor que o
            # pipeline o que aconteceu, e reinterpretar aqui só perderia informação.
            fail(
                payload.get("error", f"a etapa de {label} falhou"),
                code=code or FAILED,
                hint=payload.get("hint"),
                stage=label,
                **{k: v for k, v in payload.items() if k not in {"ok", "error", "hint"}},
            )

        results[script.removesuffix(".py")] = payload

    download, transcribe = results["download"], results["transcribe"]
    elapsed = time.monotonic() - started

    reused = [
        label
        for (label, script) in STAGES
        if results[script.removesuffix(".py")].get("reused")
    ]
    if reused:
        log(f"aproveitado do que já existia: {', '.join(reused)}")
    log(f"pipeline completo em {elapsed:.0f}s")

    succeed(
        folder=download["folder"],
        title=download.get("title"),
        duration=download.get("duration"),
        video=download.get("video"),
        audio=results["extract_audio"].get("audio"),
        transcript=transcribe.get("transcript"),
        srt=transcribe.get("srt"),
        json_file=transcribe.get("json"),
        language=transcribe.get("language"),
        model=transcribe.get("model"),
        reused_stages=reused,
        seconds=round(elapsed, 1),
    )


if __name__ == "__main__":
    main()
