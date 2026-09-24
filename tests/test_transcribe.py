"""Testes da transcrição.

O modelo em si não é exercitado aqui — depende da GPU e leva minutos. O que
cabe em teste é tudo que decide *como* ele será usado: onde o áudio é cortado,
qual modelo cabe na memória livre, e o que é feito da resposta depois.
"""

import itertools
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import transcribe

SCRIPT = ROOT / "scripts" / "transcribe.py"


class TestModelChoice:
    def test_takes_the_larger_model_when_there_is_room(self):
        _, name, _ = transcribe.choose_model(3500)
        assert name == "Qwen3-ASR-1.7B"

    def test_falls_back_to_the_smaller_one_when_memory_is_tight(self):
        _, name, _ = transcribe.choose_model(2000)
        assert name == "Qwen3-ASR-0.6B"

    def test_without_a_visible_gpu_it_still_picks_something(self):
        """Rodar devagar na CPU é melhor que não rodar."""
        _, name, _ = transcribe.choose_model(None)
        assert name == "Qwen3-ASR-0.6B"

    def test_very_little_memory_still_yields_a_choice_rather_than_a_crash(self):
        _, name, _ = transcribe.choose_model(300)
        assert name == "Qwen3-ASR-0.6B"

    def test_an_explicit_request_wins_over_the_measurement(self):
        _, name, _ = transcribe.choose_model(500, "Qwen3-ASR-1.7B")
        assert name == "Qwen3-ASR-1.7B"


class TestChunkPlanning:
    def test_cuts_in_the_middle_of_the_silence(self):
        """O meio do silêncio é o ponto mais longe das palavras dos dois lados."""
        chunks = transcribe.plan_chunks(100.0, [(40.0, 42.0)], target=30.0, maximum=120.0)

        assert chunks[0].end == 41.0
        assert chunks[1].start == 41.0

    def test_ignores_silences_that_would_make_a_chunk_shorter_than_the_target(self):
        silences = [(5.0, 5.5), (10.0, 10.5), (40.0, 40.5)]

        chunks = transcribe.plan_chunks(60.0, silences, target=30.0, maximum=120.0)

        assert [round(c.end, 2) for c in chunks] == [40.25, 60.0]

    def test_covers_the_whole_audio_without_gaps_or_overlaps(self):
        silences = [(float(t), float(t) + 0.5) for t in range(20, 300, 20)]

        chunks = transcribe.plan_chunks(300.0, silences, target=30.0, maximum=120.0)

        assert chunks[0].start == 0.0
        assert abs(chunks[-1].end - 300.0) < 0.01
        for previous, following in itertools.pairwise(chunks):
            assert previous.end == following.start

    def test_cuts_hard_when_music_leaves_no_silence_to_cut_on(self):
        """Trilha sonora contínua não produz silêncio; sem teto o chunk cresceria sem limite."""
        chunks = transcribe.plan_chunks(400.0, [], target=30.0, maximum=120.0)

        assert all(c.duration <= 120.0 + 0.01 for c in chunks)
        assert abs(chunks[-1].end - 400.0) < 0.01

    def test_falls_back_to_the_quietest_point_when_no_real_pause_exists(self):
        """Reel com trilha sonora nunca silencia de fato; cortar no seco parte palavras."""
        chunks = transcribe.plan_chunks(
            120.0, [], target=30.0, maximum=45.0, weak_silences=[(38.0, 38.2)]
        )

        assert chunks[0].end == 38.1, "deveria cortar no ponto mais quieto, não no limite"

    def test_a_real_pause_wins_over_a_merely_quiet_moment(self):
        chunks = transcribe.plan_chunks(
            120.0, [(35.0, 36.0)], target=30.0, maximum=45.0, weak_silences=[(31.0, 31.1)]
        )

        assert chunks[0].end == 35.5

    def test_cuts_hard_only_when_neither_kind_of_pause_is_available(self):
        chunks = transcribe.plan_chunks(200.0, [], target=30.0, maximum=45.0, weak_silences=[])

        assert chunks[0].end == 45.0

    def test_does_not_leave_a_sliver_at_the_end(self):
        """Uma sobra de dois segundos como chunk próprio não ajuda ninguém."""
        chunks = transcribe.plan_chunks(47.0, [], target=30.0, maximum=45.0)

        assert len(chunks) == 1
        assert chunks[0].end == 47.0

    def test_audio_shorter_than_the_target_stays_in_one_piece(self):
        chunks = transcribe.plan_chunks(12.0, [], target=30.0, maximum=120.0)

        assert len(chunks) == 1
        assert chunks[0].start == 0.0


class TestResponseCleaning:
    def test_pulls_the_text_out_of_the_model_envelope(self):
        text, language = transcribe.clean("language Portuguese<asr_text>Olá mundo.</asr_text>")

        assert text == "Olá mundo."
        assert language == "Portuguese"

    def test_survives_a_response_without_the_closing_tag(self):
        text, _ = transcribe.clean("language Portuguese<asr_text>Texto cortado")
        assert text == "Texto cortado"

    def test_collapses_the_loop_a_model_falls_into_on_ambiguous_audio(self):
        looped = "Início. " + "Inscreva-se no canal. " * 8 + "Fim."

        cleaned = transcribe.collapse_repetitions(looped)

        assert cleaned.count("Inscreva-se no canal.") < 8
        assert cleaned.startswith("Início.")
        assert cleaned.endswith("Fim.")

    def test_discards_the_hallucination_a_silent_video_produces(self):
        """Um Reel só com música fez o modelo devolver centenas de 嗯 — não havia fala."""
        assert transcribe.collapse_repetitions("嗯" * 400) == ""
        # Dois caracteres para trinta segundos de áudio: não havia fala.
        assert transcribe.collapse_repetitions("嗯。", duration=30) == ""

    def test_collapses_a_word_looped_in_sequence(self):
        assert transcribe.collapse_repetitions("e e e e e e pronto.") == "e pronto."

    def test_does_not_discard_a_short_but_real_transcription(self):
        """Textos curtos de verdade têm variedade; o critério é a pobreza, não o tamanho."""
        assert transcribe.collapse_repetitions("Oi, tudo bem?", duration=30) == "Oi, tudo bem?"
        assert transcribe.collapse_repetitions("Bom dia.", duration=3) == "Bom dia."

    def test_keeps_a_phrase_that_genuinely_repeats_a_couple_of_times(self):
        text = "Ele disse não. Ela respondeu sim. Ele disse não."

        assert transcribe.collapse_repetitions(text) == text


class TestSubtitleFormat:
    def test_formats_timestamps_the_way_srt_expects(self):
        assert transcribe.to_timestamp(0) == "00:00:00,000"
        assert transcribe.to_timestamp(3661.5) == "01:01:01,500"
        assert transcribe.to_timestamp(59.999) == "00:00:59,999"

    def test_writes_the_three_formats_with_matching_content(self, tmp_path: Path):
        chunks = [
            transcribe.Chunk(0.0, 30.0, "Primeira parte."),
            transcribe.Chunk(30.0, 61.5, "Segunda parte."),
        ]

        transcribe.write_outputs(tmp_path, chunks, "Portuguese", {"transcription_model": "teste"})

        srt = (tmp_path / "transcript.srt").read_text(encoding="utf-8")
        assert "1\n00:00:00,000 --> 00:00:30,000\nPrimeira parte." in srt
        assert "2\n00:00:30,000 --> 00:01:01,500\nSegunda parte." in srt

        data = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
        assert data["language"] == "Portuguese"
        assert data["text"] == "Primeira parte. Segunda parte."
        assert data["segments"][1]["start"] == 30.0
        assert data["transcription_model"] == "teste"

        assert "Primeira parte." in (tmp_path / "transcript.txt").read_text(encoding="utf-8")

    def test_chunks_without_text_do_not_become_empty_subtitles(self, tmp_path: Path):
        chunks = [
            transcribe.Chunk(0.0, 10.0, "Tem texto."),
            transcribe.Chunk(10.0, 20.0, ""),
            transcribe.Chunk(20.0, 30.0, "Tem texto também."),
        ]

        transcribe.write_outputs(tmp_path, chunks, None, {})

        srt = (tmp_path / "transcript.srt").read_text(encoding="utf-8")
        assert srt.count("-->") == 2
        assert "2\n00:00:20,000" in srt  # renumerado, sem buraco


class TestCommandLine:
    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False
        )

    def test_a_folder_without_audio_points_at_the_step_that_was_skipped(self, tmp_path: Path):
        result = self.run(str(tmp_path))

        assert result.returncode == transcribe.USAGE
        assert "extração de áudio" in json.loads(result.stdout)["hint"]

    def test_an_unknown_model_is_refused_before_anything_heavy_starts(self, tmp_path: Path):
        (tmp_path / "audio.wav").write_bytes(b"")

        result = self.run(str(tmp_path), "--model", "whisper-tiny")

        assert result.returncode == transcribe.USAGE
        assert "Qwen3-ASR" in json.loads(result.stdout)["hint"]
