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
    def test_reports_which_stages_were_reused(self, monkeypatch, capsys):
        responses = {
            script: ({**payload, "reused": True}, code)
            for script, (payload, code) in SUCCESSFUL.items()
        }
        fake_stages(monkeypatch, responses)

        run_main(monkeypatch)

        payload = json.loads(capsys.readouterr().out)
        assert payload["reused_stages"] == ["download", "extração de áudio", "transcrição"]

    def test_a_partially_done_run_reports_only_what_was_reused(self, monkeypatch, capsys):
        responses = dict(SUCCESSFUL)
        responses["download.py"] = ({**SUCCESSFUL["download.py"][0], "reused": True}, 0)
        fake_stages(monkeypatch, responses)

        run_main(monkeypatch)

        assert json.loads(capsys.readouterr().out)["reused_stages"] == ["download"]


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
