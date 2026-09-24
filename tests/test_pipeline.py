"""Testes do encadeamento.

Nenhuma etapa real é executada: o que se testa aqui é como o pipeline reage ao
que elas respondem. As etapas têm testes próprios, e repeti-las aqui só tornaria
a suíte lenta sem cobrir nada novo.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pipeline

SCRIPT = ROOT / "scripts" / "pipeline.py"


def fake_stages(monkeypatch, responses: dict[str, tuple[dict, int]]):
    """Substitui a execução das etapas por respostas dadas, registrando as chamadas."""
    calls: list[tuple[str, list[str]]] = []

    def run_stage(script: str, arguments: list[str]):
        calls.append((script, arguments))
        return responses[script]

    monkeypatch.setattr(pipeline, "run_stage", run_stage)
    return calls


def run_main(monkeypatch, url: str = "https://www.youtube.com/watch?v=x") -> SystemExit:
    monkeypatch.setattr(sys, "argv", ["pipeline.py", url])
    try:
        pipeline.main()
    except SystemExit as exit_signal:
        return exit_signal
    raise AssertionError("main() deveria ter encerrado via succeed/fail")


SUCCESSFUL = {
    "download.py": (
        {
            "ok": True,
            "folder": "downloads/2020-01-01-video",
            "video": "downloads/2020-01-01-video/video.mp4",
            "title": "Um vídeo",
            "duration": 120,
        },
        0,
    ),
    "extract_audio.py": (
        {"ok": True, "audio": "downloads/2020-01-01-video/audio.wav"},
        0,
    ),
    "transcribe.py": (
        {
            "ok": True,
            "transcript": "downloads/2020-01-01-video/transcript.txt",
            "srt": "downloads/2020-01-01-video/transcript.srt",
            "json": "downloads/2020-01-01-video/transcript.json",
            "language": "Portuguese",
            "model": "Qwen3-ASR-0.6B",
        },
        0,
    ),
}


class TestHappyPath:
    def test_runs_the_three_stages_in_order(self, monkeypatch, capsys):
        calls = fake_stages(monkeypatch, SUCCESSFUL)

        run_main(monkeypatch)

        assert [script for script, _ in calls] == [
            "download.py",
            "extract_audio.py",
            "transcribe.py",
        ]

    def test_passes_the_downloaded_folder_to_the_later_stages(self, monkeypatch, capsys):
        calls = fake_stages(monkeypatch, SUCCESSFUL)

        run_main(monkeypatch)

        assert calls[1][1][0] == "downloads/2020-01-01-video"
        assert calls[2][1][0] == "downloads/2020-01-01-video"

    def test_gathers_everything_the_stages_produced(self, monkeypatch, capsys):
        fake_stages(monkeypatch, SUCCESSFUL)

        run_main(monkeypatch)

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["title"] == "Um vídeo"
        assert payload["video"].endswith("video.mp4")
        assert payload["audio"].endswith("audio.wav")
        assert payload["srt"].endswith("transcript.srt")
        assert payload["language"] == "Portuguese"
        assert payload["model"] == "Qwen3-ASR-0.6B"


class TestFailurePropagation:
    def test_stops_at_the_failing_stage_and_names_it(self, monkeypatch, capsys):
        responses = dict(SUCCESSFUL)
        responses["download.py"] = (
            {"ok": False, "error": "vídeo privado", "hint": "peça um link público"},
            1,
        )
        calls = fake_stages(monkeypatch, responses)

        exit_signal = run_main(monkeypatch)

        assert exit_signal.code == 1
        assert len(calls) == 1, "as etapas seguintes não deveriam ter rodado"
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "download"

    def test_preserves_the_exit_code_and_the_hint_of_the_stage(self, monkeypatch, capsys):
        """A etapa sabe melhor que o pipeline o que houve; reinterpretar perderia informação."""
        responses = dict(SUCCESSFUL)
        responses["extract_audio.py"] = (
            {"ok": False, "error": "ffmpeg não foi encontrado", "hint": "instale o ffmpeg"},
            3,
        )
        fake_stages(monkeypatch, responses)

        exit_signal = run_main(monkeypatch)

        assert exit_signal.code == 3
        payload = json.loads(capsys.readouterr().out)
        assert payload["hint"] == "instale o ffmpeg"
        assert payload["stage"] == "extração de áudio"

    def test_a_stage_that_answers_gibberish_is_reported_rather_than_crashing(
        self, monkeypatch, capsys
    ):
        responses = dict(SUCCESSFUL)
        responses["transcribe.py"] = (
            {"ok": False, "error": "transcribe.py não devolveu um resultado legível"},
            1,
        )
        fake_stages(monkeypatch, responses)

        exit_signal = run_main(monkeypatch)

        assert exit_signal.code == 1
        assert json.loads(capsys.readouterr().out)["stage"] == "transcrição"


class TestResumption:
    """Com vários vídeos por post, "quais etapas" deixou de ter resposta única —
    daí o resultado dizer apenas se havia algo pronto para aproveitar."""

    def test_says_nothing_was_redone_when_everything_already_existed(self, monkeypatch, capsys):
        responses = {
            script: ({**payload, "reused": True}, code)
            for script, (payload, code) in SUCCESSFUL.items()
        }
        fake_stages(monkeypatch, responses)

        run_main(monkeypatch)

        assert json.loads(capsys.readouterr().out)["reused"] is True

    def test_a_partially_done_run_still_counts_as_work_performed(self, monkeypatch, capsys):
        """Só o download estava pronto; áudio e transcrição rodaram de verdade."""
        responses = dict(SUCCESSFUL)
        responses["download.py"] = ({**SUCCESSFUL["download.py"][0], "reused": True}, 0)
        fake_stages(monkeypatch, responses)

        run_main(monkeypatch)

        assert json.loads(capsys.readouterr().out)["reused"] is False


class TestCarousel:
    """Um post com vários vídeos passa cada um pelas mesmas etapas."""

    def test_runs_the_later_stages_once_per_video(self, monkeypatch, capsys):
        responses = dict(SUCCESSFUL)
        responses["download.py"] = (
            {
                "ok": True,
                "folder": "downloads/post-01",
                "items": [
                    {"folder": "downloads/post-01", "video": "downloads/post-01/video.mp4",
                     "title": "Post", "duration": 10},
                    {"folder": "downloads/post-02", "video": "downloads/post-02/video.mp4",
                     "title": "Post", "duration": 12},
                ],
            },
            0,
        )
        calls = fake_stages(monkeypatch, responses)

        run_main(monkeypatch)

        scripts = [script for script, _ in calls]
        assert scripts.count("extract_audio.py") == 2
        assert scripts.count("transcribe.py") == 2
        assert calls[1][1][0] == "downloads/post-01"
        assert calls[3][1][0] == "downloads/post-02"

    def test_reports_every_video_it_produced(self, monkeypatch, capsys):
        responses = dict(SUCCESSFUL)
        responses["download.py"] = (
            {
                "ok": True,
                "folder": "downloads/post-01",
                "items": [
                    {"folder": "downloads/post-01", "title": "Post"},
                    {"folder": "downloads/post-02", "title": "Post"},
                ],
            },
            0,
        )
        fake_stages(monkeypatch, responses)

        run_main(monkeypatch)

        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 2
        assert len(payload["videos"]) == 2
        assert payload["folder"] == "downloads/post-01"

    def test_one_silent_video_does_not_sink_the_others(self, monkeypatch, capsys):
        """Num carrossel real, o sexto vídeo não tinha faixa de áudio e derrubava o post inteiro."""
        calls_seen: list[str] = []

        def run_stage(script: str, arguments: list[str]):
            calls_seen.append(f"{script}:{arguments[0]}")
            if script == "extract_audio.py" and arguments[0].endswith("-02"):
                return {"ok": False, "error": "video.mp4 não tem faixa de áudio"}, 1
            if script == "download.py":
                return (
                    {
                        "ok": True,
                        "folder": "downloads/post-01",
                        "items": [
                            {"folder": "downloads/post-01", "title": "Post"},
                            {"folder": "downloads/post-02", "title": "Post"},
                            {"folder": "downloads/post-03", "title": "Post"},
                        ],
                    },
                    0,
                )
            return SUCCESSFUL[script]

        monkeypatch.setattr(pipeline, "run_stage", run_stage)
        run_main(monkeypatch)

        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["count"] == 2, "os dois vídeos sadios precisam sobreviver"
        assert payload["skipped"][0]["folder"] == "downloads/post-02"
        assert "transcribe.py:downloads/post-03" in calls_seen

    def test_an_environment_failure_stops_everything_instead_of_repeating(
        self, monkeypatch, capsys
    ):
        """Falta de ffmpeg vai falhar em todos; insistir só repetiria a mensagem."""

        def run_stage(script: str, arguments: list[str]):
            if script == "download.py":
                return (
                    {
                        "ok": True,
                        "folder": "downloads/post-01",
                        "items": [
                            {"folder": "downloads/post-01"},
                            {"folder": "downloads/post-02"},
                        ],
                    },
                    0,
                )
            return {"ok": False, "error": "ffmpeg não foi encontrado"}, 3

        monkeypatch.setattr(pipeline, "run_stage", run_stage)
        exit_signal = run_main(monkeypatch)

        assert exit_signal.code == 3

    def test_a_post_where_nothing_works_is_a_failure_not_an_empty_success(
        self, monkeypatch, capsys
    ):
        def run_stage(script: str, arguments: list[str]):
            if script == "download.py":
                return (
                    {
                        "ok": True,
                        "folder": "downloads/post-01",
                        "items": [
                            {"folder": "downloads/post-01"},
                            {"folder": "downloads/post-02"},
                        ],
                    },
                    0,
                )
            return {"ok": False, "error": "sem faixa de áudio"}, 1

        monkeypatch.setattr(pipeline, "run_stage", run_stage)
        exit_signal = run_main(monkeypatch)

        assert exit_signal.code == 1
        assert "nenhum dos vídeos" in json.loads(capsys.readouterr().out)["error"]

    def test_a_single_video_does_not_grow_a_videos_list(self, monkeypatch, capsys):
        fake_stages(monkeypatch, SUCCESSFUL)

        run_main(monkeypatch)

        payload = json.loads(capsys.readouterr().out)
        assert payload["count"] == 1
        assert payload["videos"] is None


class TestCommandLine:
    def test_an_unsupported_url_fails_in_the_download_stage(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "https://vimeo.com/123"],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )

        assert result.returncode == 2
        payload = json.loads(result.stdout)
        assert payload["stage"] == "download"
        assert "YouTube" in payload["hint"]
