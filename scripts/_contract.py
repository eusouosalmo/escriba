"""Contrato de I/O entre os scripts e as skills que os invocam.

A regra é uma só: **stdout carrega exatamente um objeto JSON**, e nada mais.
Progresso, avisos e log humano vão para stderr. Isso permite que uma skill
leia o resultado com `json.loads(stdout)` sem precisar garimpar texto.

O exit code diz o que aconteceu; o JSON diz os detalhes.
"""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

# Exit codes. Poucos e com significado distinto — cada um leva a uma
# reação diferente da skill que chamou o script.
OK = 0
FAILED = 1  # falha esperada: vídeo privado, sem áudio, rate limit
USAGE = 2  # argumentos inválidos — erro de quem chamou
ENVIRONMENT = 3  # dependência ausente ou ambiente incapaz


def log(message: str) -> None:
    """Escreve uma linha de progresso em stderr, fora do canal de dados."""
    print(message, file=sys.stderr, flush=True)


def succeed(**data: Any) -> NoReturn:
    """Emite o resultado e encerra com sucesso."""
    json.dump({"ok": True, **data}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(OK)


def fail(error: str, *, code: int = FAILED, hint: str | None = None, **data: Any) -> NoReturn:
    """Emite a falha no mesmo formato do sucesso e encerra com o código dado.

    `hint` existe para o caso em que a causa é conhecida e acionável — por
    exemplo, um 403 do YouTube que se resolve atualizando o yt-dlp. A skill
    repassa essa dica ao usuário em vez de adivinhar.
    """
    payload: dict[str, Any] = {"ok": False, "error": error, **data}
    if hint:
        payload["hint"] = hint
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(code)
