"""O contrato é a fronteira entre os scripts e as skills.

Os testes rodam os helpers em subprocesso de propósito: o que importa não é
o valor de retorno da função, e sim o que sai em stdout, o que sai em stderr
e qual exit code chega a quem invocou.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def run(body: str) -> subprocess.CompletedProcess[str]:
    code = f"import sys; sys.path.insert(0, {str(SCRIPTS)!r}); from _contract import *\n{body}"
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )


def test_succeed_emits_single_json_object_and_exits_zero():
    result = run("succeed(path='/tmp/x', duration=42)")

    assert result.returncode == 0
    assert json.loads(result.stdout) == {"ok": True, "path": "/tmp/x", "duration": 42}


def test_fail_uses_the_same_shape_and_the_given_exit_code():
    result = run("fail('vídeo privado', code=FAILED, url='https://x')")

    assert result.returncode == 1
    assert json.loads(result.stdout) == {
        "ok": False,
        "error": "vídeo privado",
        "url": "https://x",
    }


def test_fail_carries_an_actionable_hint_when_there_is_one():
    result = run("fail('403 do YouTube', hint='atualize o yt-dlp')")

    assert json.loads(result.stdout)["hint"] == "atualize o yt-dlp"


def test_usage_and_environment_have_distinct_exit_codes():
    assert run("fail('args', code=USAGE)").returncode == 2
    assert run("fail('sem ffmpeg', code=ENVIRONMENT)").returncode == 3


def test_log_goes_to_stderr_and_never_pollutes_the_json():
    result = run("log('baixando...'); succeed(path='/tmp/x')")

    assert result.stderr.strip() == "baixando..."
    assert json.loads(result.stdout) == {"ok": True, "path": "/tmp/x"}


def test_accents_survive_the_round_trip():
    result = run("fail('não foi possível extrair áudio')")

    assert json.loads(result.stdout)["error"] == "não foi possível extrair áudio"
