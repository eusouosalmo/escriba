"""Testes das decisões que o script toma antes e depois da rede.

O download em si não é testado aqui — depende do YouTube e é lento. O que
cabe em teste é o que decide onde o arquivo vai parar, o que é aceito como
entrada e como uma falha conhecida vira mensagem acionável.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import download


class TestSlugify:
    def test_strips_accents_and_punctuation(self):
        assert download.slugify("Relatividade Restrita: o que é?") == "relatividade-restrita-o-que-e"

    def test_collapses_separators_and_trims_edges(self):
        assert download.slugify("  --  Olá   /  mundo -- ") == "ola-mundo"

    def test_truncates_on_a_word_boundary(self):
        slug = download.slugify("palavra " * 30, limit=20)
        assert len(slug) <= 20
        assert not slug.endswith("-")

    def test_falls_back_when_nothing_survives(self):
        assert download.slugify("日本語 🎬") == "sem-titulo"


class TestDescribe:
    """O Instagram não entrega título; o nome da pasta precisa sair de outro lugar."""

    def test_prefers_the_title_when_the_source_has_one(self):
        assert download.describe({"title": "Um título", "description": "legenda"}) == "Um título"

    def test_falls_back_to_the_caption_when_there_is_no_title(self):
        assert download.describe({"description": "Receita de pão"}) == "Receita de pão"

    def test_keeps_only_the_first_line_of_a_long_caption(self):
        caption = "Pão caseiro fofinho\n\n#receita #paocaseiro #comida @alguem"

        assert download.describe({"description": caption}) == "Pão caseiro fofinho"

    def test_uses_the_author_when_the_caption_is_empty(self):
        assert download.describe({"description": "  ", "uploader": "cozinha_da_ana"}) == "cozinha_da_ana"

    def test_falls_back_to_the_id_when_nothing_else_exists(self):
        assert download.describe({"id": "CxYz123"}) == "CxYz123"


class TestFolderName:
    def test_uses_the_publication_date_when_there_is_one(self):
        name = download.folder_name({"upload_date": "20200524", "title": "Buracos Negros"})
        assert name == "2020-05-24-buracos-negros"

    def test_falls_back_to_today_when_the_source_omits_the_date(self):
        name = download.folder_name({"title": "Sem data"})
        assert name.endswith("-sem-data")
        assert len(name.split("-sem-data")[0]) == 10

    def test_an_instagram_post_without_title_still_gets_a_readable_folder(self):
        name = download.folder_name(
            {"description": "Pão caseiro fofinho\n#receita", "id": "CxYz", "upload_date": "20240301"}
        )

        assert name == "2024-03-01-pao-caseiro-fofinho"

    def test_a_post_with_only_emoji_still_gets_a_usable_name(self):
        name = download.folder_name({"description": "🔥🍞", "uploader": "cozinha", "id": "CxYz"})

        assert name.endswith("-cozinha")


class TestVersionComparison:
    def test_orders_calendar_versions_numerically(self):
        # "2026.8.19" contra "2026.08.19" quebraria numa comparação textual
        assert download.parse_version("2026.8.19") == download.parse_version("2026.08.19")
        assert download.parse_version("2026.03.17") < download.parse_version("2026.8.19")


class TestKnownFailures:
    @pytest.mark.parametrize(
        ("message", "expected_fragment"),
        [
            ("ERROR: Private video. Sign in if you've been granted access", "privado"),
            ("ERROR: Video unavailable", "não está disponível"),
            ("ERROR: The uploader has blocked it in your country", "bloqueado na sua região"),
            ("ERROR: unable to download: HTTP Error 429: Too Many Requests", "limitou a taxa"),
        ],
    )
    def test_recognised_errors_become_readable_messages(self, message, expected_fragment):
        description, hint = download.describe_failure(Exception(message))
        assert expected_fragment in description
        assert hint

    @pytest.mark.parametrize(
        ("message", "expected_fragment"),
        [
            ("ERROR: Login required to access this content", "exige login"),
            ("ERROR: You need to log in to access this content", "pediu login"),
            ("ERROR: Unable to extract shared data", "não conseguiu ler a página"),
        ],
    )
    def test_instagram_failures_are_explained_in_terms_of_scope(self, message, expected_fragment):
        description, hint = download.describe_failure(Exception(message))

        assert expected_fragment in description
        assert hint

    def test_a_broken_instagram_extractor_suggests_updating_rather_than_blaming_the_user(self):
        _, hint = download.describe_failure(Exception("ERROR: Unable to extract shared data"))

        assert "yt-dlp" in hint

    def test_a_post_without_video_says_so_plainly(self):
        description, hint = download.describe_failure(
            Exception("ERROR: [Instagram] abc: No video formats found!")
        )

        assert "não tem vídeo" in description
        assert "transcrever" in hint

    def test_the_403_hint_points_at_the_real_cause(self):
        _, hint = download.describe_failure(Exception("HTTP Error 403: Forbidden"))
        assert "yt-dlp" in hint

    def test_unknown_errors_are_passed_through_without_inventing_a_hint(self):
        description, hint = download.describe_failure(Exception("algo totalmente novo"))
        assert description == "algo totalmente novo"
        assert hint is None


class TestCarousel:
    """Um post do Instagram pode misturar fotos e vídeos na mesma URL."""

    def test_a_single_video_post_is_not_treated_as_a_carousel(self):
        assert download.video_items({"id": "abc", "formats": [{"vcodec": "h264"}]}) == []

    def test_picks_only_the_entries_that_actually_have_video(self):
        info = {
            "entries": [
                {"id": "foto", "formats": [{"vcodec": "none", "acodec": "none"}]},
                {"id": "video", "formats": [{"vcodec": "h264"}]},
            ]
        }

        found = download.video_items(info)

        assert [entry["id"] for _, entry in found] == ["video"]

    def test_skips_entries_the_extractor_could_not_read(self):
        """Itens ilegíveis viram None e são quase sempre fotos."""
        info = {"entries": [None, {"id": "video", "duration": 12}, None]}

        found = download.video_items(info)

        assert len(found) == 1

    def test_keeps_the_original_position_because_that_is_how_ytdlp_addresses_them(self):
        info = {
            "entries": [
                None,
                {"id": "foto", "formats": []},
                {"id": "video", "formats": [{"vcodec": "h264"}]},
            ]
        }

        (position, entry), = download.video_items(info)

        assert position == 3, "posição é 1-based e conta os itens pulados"
        assert entry["id"] == "video"


class TestQualityCeiling:
    def test_caps_the_resolution_by_default(self):
        options = download.build_options(None, "out.%(ext)s")
        assert "height<=1080" in options["format"]

    def test_lifts_the_cap_when_asked(self):
        options = download.build_options(None, "out.%(ext)s", None)
        assert "height" not in options["format"]

    def test_metadata_only_calls_do_not_set_a_format(self):
        assert "format" not in download.build_options(None)


class TestNodeDiscovery:
    def test_prefers_whatever_is_on_the_path(self, monkeypatch):
        monkeypatch.setattr(download.shutil, "which", lambda _: "/usr/bin/node")
        assert download.find_node() == "/usr/bin/node"

    def test_picks_the_newest_nvm_install_when_the_path_is_empty(self, monkeypatch, tmp_path):
        for version in ("v22.12.0", "v24.18.0", "v24.9.0"):
            binary = tmp_path / ".nvm/versions/node" / version / "bin/node"
            binary.parent.mkdir(parents=True)
            binary.touch()
        monkeypatch.setattr(download.shutil, "which", lambda _: None)
        monkeypatch.setattr(download.Path, "home", classmethod(lambda _: tmp_path))

        assert "v24.18.0" in download.find_node()


class TestCommandLine:
    """Fronteira de verdade: o que o script devolve a quem o chamou."""

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "download.py"), *args],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )

    def test_rejects_something_that_is_not_a_url(self):
        result = self.run("isso-nao-e-uma-url")

        assert result.returncode == download.USAGE
        assert json.loads(result.stdout)["ok"] is False

    def test_rejects_a_platform_we_cannot_handle_yet_and_says_which(self):
        result = self.run("https://vimeo.com/123456")

        assert result.returncode == download.USAGE
        payload = json.loads(result.stdout)
        assert payload["platform"] == "vimeo.com"
        assert "YouTube" in payload["hint"]
        assert "Instagram" in payload["hint"]
