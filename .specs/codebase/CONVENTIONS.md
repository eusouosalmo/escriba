# Convenções

## Contrato entre scripts e skills

O trabalho determinístico mora em `scripts/`. As skills invocam esses scripts e leem o resultado.
A fronteira entre os dois é estreita de propósito:

- **stdout carrega exatamente um objeto JSON**, e nada além disso. A skill lê com `json.loads` sem garimpar texto.
- **stderr carrega o log humano** — progresso, avisos, saída de ferramentas externas.
- **O exit code diz o que aconteceu**; o JSON diz os detalhes.

Todo resultado tem o campo `ok`. Sucesso e falha têm o mesmo formato, o que evita dois caminhos de parsing.

| Code | Constante | Significado | Reação esperada da skill |
|---|---|---|---|
| 0 | `OK` | Deu certo | Seguir para a próxima etapa |
| 1 | `FAILED` | Falha esperada (vídeo privado, sem áudio, rate limit) | Relatar ao usuário com a causa |
| 2 | `USAGE` | Argumentos inválidos | Corrigir a chamada — o erro é de quem chamou |
| 3 | `ENVIRONMENT` | Dependência ausente ou ambiente incapaz | Orientar a instalação |

Quando a causa é conhecida e acionável, o script preenche `hint` com o que resolve
(por exemplo, um 403 do YouTube que se corrige atualizando o yt-dlp). A skill repassa
a dica em vez de adivinhar.

Use `scripts/_contract.py`: `succeed(**dados)`, `fail(erro, code=..., hint=...)` e `log(msg)`.

## Idioma

Identificadores e docstrings em inglês, seguindo o idioma das bibliotecas e do próprio Python.
Mensagens destinadas ao usuário — o campo `error`, o `hint`, o texto do `log` — em português,
porque é nesse idioma que elas serão lidas. Documentação do projeto em português.

## Ambiente

Dependências são gerenciadas por `uv` e declaradas em `pyproject.toml`. Os scripts rodam via
`uv run`, nunca contra o Python do sistema.

O `yt-dlp` é dependência declarada por decisão, não por conveniência: a versão do sistema
quebra com `403 Forbidden` no YouTube depois de alguns meses (ver `STATE.md`, L-002).

`node` está instalado via nvm, então o binário só existe no PATH de shells que carregaram o nvm.
Scripts que dependem do runtime JavaScript do yt-dlp precisam localizar o `node` explicitamente
em vez de supor que ele está no PATH.

## Testes

`pytest`, em `tests/`. Testes de fronteira (como o do contrato) rodam o código em subprocesso,
porque o que importa ali é o que chega a stdout, stderr e ao exit code — não o valor de retorno
da função.

## Saída em disco

Uma pasta por vídeo em `downloads/<data>-<titulo-slug>/`, contendo vídeo, áudio, as transcrições
e o `metadata.json`. O caminho dessa pasta é o identificador que circula entre as skills do pipeline.

`downloads/` e qualquer mídia estão no `.gitignore` — nunca entram no repositório.
