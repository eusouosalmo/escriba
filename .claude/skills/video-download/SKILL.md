---
name: video-download
description: Baixa um vídeo do YouTube ou do Instagram para uma pasta própria em downloads/, com metadata.json registrando procedência. Use sempre que o usuário fornecer um link de vídeo e quiser baixá-lo, arquivá-lo ou preparar o material para transcrição — inclusive quando ele só colar a URL, ou disser coisas como "pega esse vídeo", "baixa esse link", "salva esse vídeo aí". É também o primeiro passo obrigatório de qualquer pedido de transcrição de vídeo do YouTube.
---

# Baixar vídeo

O trabalho é feito por `scripts/download.py`. Esta skill existe para invocá-lo com os
argumentos certos e traduzir o resultado — não para reimplementar nada do que ele faz.

## Como invocar

Sempre a partir da raiz do projeto:

```bash
uv run python scripts/download.py "<URL>"
```

O `uv run` não é detalhe: ele garante o yt-dlp do projeto. O binário do sistema pode ser
uma versão antiga que falha com 403 no YouTube, e a falha se disfarça de problema do vídeo.

Opções, quando fizerem falta:

- `--max-height 0` — baixa a melhor qualidade disponível. O padrão é 1080p porque sem teto
  um vídeo de 10 minutos passa de 480 MB em 4K, e o destino aqui é transcrever, não arquivar
  em qualidade de cinema. Use apenas se o usuário pedir qualidade máxima.
- `--force` — rebaixa mesmo que o vídeo já esteja em disco.
- `--output-dir <dir>` — muda a raiz de saída. Raramente necessário.

## Como ler o resultado

O script escreve **um objeto JSON em stdout**; o resto é log humano em stderr e pode ser
ignorado em caso de sucesso. O exit code diz o que aconteceu:

| Code | Significado | O que fazer |
|---|---|---|
| 0 | Deu certo | Seguir. O campo `folder` é o que as próximas etapas usam. |
| 1 | Falha esperada | Contar ao usuário o `error` e, quando houver, o `hint` — ele costuma ser a solução. |
| 2 | Entrada inválida | O erro é da chamada, não do usuário. Corrija a URL ou explique o que é aceito. |
| 3 | Ambiente incapaz | Siga o `hint` (normalmente `uv sync` ou atualizar o yt-dlp). |

Em caso de sucesso, `reused: true` significa que o vídeo já estava em disco e nada foi
baixado de novo. Vale mencionar ao usuário — ele pode estar esperando um download e
estranhar a resposta instantânea.

## O que reportar ao usuário

Diga o título, a duração e onde o arquivo ficou. O caminho importa porque é o que ele vai
abrir depois.

Quando o script falhar com `hint`, repasse a dica em vez de propor sua própria teoria. O
script só preenche esse campo quando reconheceu a causa, e a causa reconhecida vale mais
que uma hipótese — em especial no 403, que quase sempre é yt-dlp velho e não vídeo com
problema.

## Limites que valem avisar antes de tentar

YouTube e Instagram, só conteúdo público. Vídeo privado, story, perfil fechado ou qualquer
coisa que exija login vai falhar, e isso é escopo, não defeito. Uma URL por vez, sem
playlists nem carrosséis.

O Instagram é notoriamente instável: ele muda sem aviso e quebra o extractor do yt-dlp. Se um
link que deveria funcionar falhar com "não conseguiu ler a página", a causa mais provável é
essa, e a dica vai sugerir atualizar o yt-dlp. Não é erro do usuário nem do link.

Se o usuário pedir algo fora disso, diga o limite de cara em vez de tentar e falhar.
