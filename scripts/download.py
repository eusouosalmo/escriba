"""Baixa um vídeo do YouTube ou do Instagram e registra sua procedência.

Usa o yt-dlp como biblioteca, e não como binário. A diferença importa: um
`yt-dlp` chamado pelo PATH pode silenciosamente ser o do sistema, que quebra com
403 depois de alguns meses (ver STATE.md, L-002 e L-009). O import só resolve
para a versão instalada pelo projeto, então a procedência fica garantida.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _contract import ENVIRONMENT, FAILED, USAGE, fail, log, succeed

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError
    from yt_dlp.version import __version__ as YTDLP_VERSION
except ImportError:  # pragma: no cover - depende do ambiente, não da lógica
    fail(
        "yt-dlp não está disponível no ambiente do projeto",
        code=ENVIRONMENT,
        hint="rode `uv sync` na raiz do projeto",
    )

MINIMUM_YTDLP = "2026.8.19"

SUPPORTED_HOSTS = {
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "m.youtube.com": "youtube",
    "music.youtube.com": "youtube",
    "youtu.be": "youtube",
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
    "m.instagram.com": "instagram",
}

# Falhas que sabemos diagnosticar. A dica é o que diferencia "deu erro" de
# "deu erro e é isso que resolve" — a skill repassa em vez de adivinhar.
KNOWN_FAILURES: list[tuple[str, str, str]] = [
    (
        "private video",
        "O vídeo é privado.",
        "só funciona com conteúdo público; peça o link de um vídeo aberto",
    ),
    (
        "sign in to confirm",
        "O YouTube pediu login para confirmar que não é um robô.",
        "costuma ser temporário; espere alguns minutos e tente de novo",
    ),
    (
        "video unavailable",
        "O vídeo não está disponível — pode ter sido removido.",
        "confira se o link ainda abre no navegador",
    ),
    (
        "blocked it in your country",
        "O vídeo está bloqueado na sua região.",
        "não há o que fazer sem contornar o bloqueio, o que está fora do escopo",
    ),
    (
        "http error 429",
        "A plataforma limitou a taxa de requisições.",
        "espere alguns minutos antes de tentar de novo",
    ),
    (
        "login required",
        "Este conteúdo exige login.",
        "só funciona com conteúdo público; stories e perfis privados estão fora do escopo",
    ),
    (
        "requested content is not available",
        "O Instagram não disponibilizou este conteúdo.",
        (
            "confira se o link abre numa janela anônima do navegador; se abrir, "
            "o extractor do yt-dlp pode ter quebrado e vale atualizá-lo"
        ),
    ),
    (
        "you need to log in",
        "O Instagram pediu login para acessar este conteúdo.",
        "só funciona com conteúdo público",
    ),
    (
        "unable to extract shared data",
        "O extractor do Instagram não conseguiu ler a página.",
        (
            "o Instagram costuma mudar sem aviso e quebrar o extractor; "
            "atualize com `uv lock --upgrade-package yt-dlp && uv sync`"
        ),
    ),
    (
        "http error 403",
        "O YouTube recusou o download com 403.",
        (
            "quase sempre é yt-dlp desatualizado; atualize com "
            f"`uv lock --upgrade-package yt-dlp` (versão atual: {YTDLP_VERSION})"
        ),
    ),
]


def parse_version(raw: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", raw))


def check_environment() -> None:
    """O yt-dlp envelhece mal: versões antigas não degradam, elas param."""
    if parse_version(YTDLP_VERSION) < parse_version(MINIMUM_YTDLP):
        fail(
            f"yt-dlp {YTDLP_VERSION} é anterior ao mínimo suportado ({MINIMUM_YTDLP})",
            code=ENVIRONMENT,
            hint="atualize com `uv lock --upgrade-package yt-dlp && uv sync`",
            ytdlp_version=YTDLP_VERSION,
        )


def identify_platform(url: str) -> str:
    """Aceita só o que sabemos baixar, e diz o que é aceito quando recusa."""
    from urllib.parse import urlparse

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        fail(
            f"{url!r} não é uma URL válida",
            code=USAGE,
            hint="informe um link completo, como https://www.youtube.com/watch?v=...",
        )

    platform = SUPPORTED_HOSTS.get(parsed.netloc.lower())
    if platform is None:
        fail(
            f"{parsed.netloc} não é uma origem suportada",
            code=USAGE,
            hint="são suportados YouTube e Instagram, apenas conteúdo público",
            platform=parsed.netloc,
        )
    return platform


def find_node() -> str | None:
    """Localiza o node sem supor que ele está no PATH.

    Quando o node vem do nvm, ele só existe no PATH de shells que carregaram o
    nvm — e um script rodando fora desse contexto não encontraria nada. Sem
    runtime JavaScript o yt-dlp degrada a extração do YouTube (ver L-003).
    """
    found = shutil.which("node")
    if found:
        return found

    candidates = sorted(Path.home().glob(".nvm/versions/node/*/bin/node"))
    if candidates:
        return str(max(candidates, key=lambda p: parse_version(p.parts[-3])))
    return None


def slugify(text: str, *, limit: int = 60) -> str:
    """Título legível vira nome de pasta previsível, sem acento nem pontuação."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")
    if len(slug) > limit:
        slug = slug[:limit].rsplit("-", 1)[0]
    return slug or "sem-titulo"


def describe(info: dict) -> str:
    """Encontra algo legível para dar nome à pasta.

    O YouTube sempre entrega um título. O Instagram não: o que existe é a
    legenda do post, que pode ser longa, vazia ou só emoji. A busca desce do
    mais informativo ao mais garantido, e o id sempre existe — assim o nome
    continua previsível mesmo quando nada mais vem.
    """
    for key in ("title", "description", "uploader", "channel", "id"):
        value = (info.get(key) or "").strip()
        if not value:
            continue
        # A primeira linha da legenda costuma ser a frase que resume o post;
        # o resto vira hashtag e menção, que não ajudam a identificar nada.
        first_line = value.splitlines()[0].strip()
        # Uma legenda só de emoji não sobrevive à transliteração e viraria um
        # nome vazio, então ela conta como ausente e a busca continua.
        if first_line and slugify(first_line) != "sem-titulo":
            return first_line
    return str(info.get("id") or "")


def folder_name(info: dict) -> str:
    """Nomeia pela data de publicação, que é o que ordena um acervo com sentido.

    Quando a origem não informa a data — acontece fora do YouTube — cai para a
    data de hoje, para o nome continuar previsível.
    """
    upload_date = info.get("upload_date")
    if upload_date and len(upload_date) == 8:
        date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    else:
        date = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{date}-{slugify(describe(info))}"


def describe_failure(error: Exception) -> tuple[str, str | None]:
    message = str(error)
    lowered = message.lower()
    for needle, description, hint in KNOWN_FAILURES:
        if needle in lowered:
            return description, hint
    return message, None


def build_options(
    node_path: str | None, outtmpl: str | None = None, max_height: int | None = 1080
) -> dict:
    options: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _StderrLogger(),
    }
    if node_path:
        # A API Python quer {runtime: {config}} aqui, e não a lista que a
        # linha de comando aceita — formatos diferentes para a mesma opção.
        options["js_runtimes"] = {"node": {"path": node_path}}
    if outtmpl:
        options["outtmpl"] = outtmpl
        # O fim do vídeo aqui é ser transcrito e consultado, não arquivado em
        # qualidade máxima: sem teto, um vídeo de 10 min chega a 480 MB em 4K.
        # 1080p mantém o vídeo assistível por uma fração do espaço e do tempo.
        if max_height:
            options["format"] = (
                f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv*+ba/b"
            )
        else:
            options["format"] = "bv*+ba/b"
        options["merge_output_format"] = "mp4"
    return options


class _StderrLogger:
    """Mantém o canal de dados limpo: o yt-dlp fala em stderr, nunca em stdout."""

    def debug(self, message: str) -> None:
        if message.startswith("[debug] "):
            return
        log(message)

    def info(self, message: str) -> None:
        log(message)

    def warning(self, message: str) -> None:
        log(f"aviso: {message}")

    def error(self, message: str) -> None:
        log(f"erro: {message}")


def existing_video(folder: Path) -> Path | None:
    if not folder.is_dir():
        return None
    for candidate in sorted(folder.iterdir()):
        if candidate.is_file() and candidate.stem == "video":
            return candidate
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa um vídeo e registra sua procedência")
    parser.add_argument("url", help="URL do vídeo")
    parser.add_argument(
        "--output-dir",
        default="downloads",
        help="raiz onde a pasta do vídeo é criada (padrão: downloads)",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=1080,
        help="altura máxima do vídeo em pixels; use 0 para baixar a melhor disponível",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="baixa de novo mesmo se o vídeo já estiver em disco",
    )
    args = parser.parse_args()

    check_environment()
    platform = identify_platform(args.url)

    node_path = find_node()
    if not node_path:
        log("aviso: nenhum runtime JavaScript encontrado — a extração pode vir incompleta")

    log("consultando metadados...")
    try:
        with YoutubeDL(build_options(node_path)) as ydl:
            info = ydl.extract_info(args.url, download=False)
    except DownloadError as error:
        description, hint = describe_failure(error)
        fail(description, code=FAILED, hint=hint, url=args.url)

    folder = Path(args.output_dir) / folder_name(info)
    already = existing_video(folder)
    if already and not args.force:
        log(f"já existe em {folder}")
        succeed(
            folder=str(folder),
            video=str(already),
            title=info.get("title"),
            duration=info.get("duration"),
            reused=True,
        )

    folder.mkdir(parents=True, exist_ok=True)
    log(f"baixando para {folder}...")
    try:
        options = build_options(
            node_path, str(folder / "video.%(ext)s"), args.max_height or None
        )
        with YoutubeDL(options) as ydl:
            ydl.download([args.url])
    except DownloadError as error:
        description, hint = describe_failure(error)
        fail(description, code=FAILED, hint=hint, url=args.url, folder=str(folder))

    video = existing_video(folder)
    if not video:
        fail(
            "o download terminou mas nenhum arquivo de vídeo foi encontrado",
            code=FAILED,
            folder=str(folder),
        )

    metadata = {
        "url": args.url,
        "platform": platform,
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "duration_seconds": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ytdlp_version": YTDLP_VERSION,
        "video_file": video.name,
        "max_height": args.max_height or None,
    }
    (folder / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    succeed(
        folder=str(folder),
        video=str(video),
        title=metadata["title"],
        duration=metadata["duration_seconds"],
        reused=False,
    )


if __name__ == "__main__":
    main()
