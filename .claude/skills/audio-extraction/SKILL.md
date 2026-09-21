---
name: audio-extraction
description: Extrai o áudio de um vídeo já baixado para WAV 16 kHz mono, o formato que o reconhecimento de fala espera. Use depois do download e antes de qualquer transcrição, e também quando o usuário pedir só o áudio de um vídeo que já está em disco — por exemplo "tira o áudio disso", "preciso do áudio desse vídeo", "converte pra wav". É etapa obrigatória do pipeline de transcrição.
---

# Extrair áudio

O trabalho é do `scripts/extract_audio.py`. Ele roda `ffmpeg` com parâmetros fixos: não há
decisão a tomar aqui, e improvisar os parâmetros só quebraria a etapa seguinte.

## Como invocar

```bash
uv run python scripts/extract_audio.py "<pasta do vídeo>"
```

O argumento é a **pasta**, não o arquivo de vídeo — é o caminho que o download devolveu no
campo `folder`, e é o identificador que circula entre todas as etapas. O áudio sai como
`audio.wav` dentro dela.

Use `--force` para extrair de novo quando o áudio já existir.

## O formato, e por que ele é fixo

16 kHz, mono, PCM 16 bits. É o que os modelos de ASR consomem. Entregar qualquer outra coisa
apenas empurra a conversão para a transcrição, que teria de refazer exatamente isto — e
provavelmente pior, porque lá o contexto sobre o arquivo original já se perdeu.

Se o usuário pedir MP3 ou outra taxa, explique que este script serve ao pipeline de
transcrição, e faça a conversão avulsa direto com `ffmpeg` em vez de alterar o script.

## Como ler o resultado

Um JSON em stdout, log em stderr. Os exit codes são os do projeto: 0 sucesso, 1 falha
esperada, 2 uso inválido, 3 ambiente incapaz.

Dois casos merecem tradução para o usuário:

**`reused: true`** — o áudio já existia e nada foi refeito. Mencione, porque a resposta
instantânea pode surpreender quem esperava uma conversão.

**Vídeo sem faixa de áudio** — falha com código 1 dizendo exatamente isso. Não é defeito do
script nem do download: o vídeo é mudo e não há o que transcrever. Diga isso com todas as
letras, em vez de sugerir tentar de novo.

## Quando a pasta não tem vídeo

Falha com código 2 e a dica de rodar o download antes. Se isso acontecer no meio de um
pipeline, o passo que falhou foi o anterior — volte para ele em vez de insistir na extração.
