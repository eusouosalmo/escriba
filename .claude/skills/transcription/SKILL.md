---
name: transcription
description: Transcreve localmente o áudio de um vídeo já baixado usando Qwen3-ASR no llama.cpp, gerando transcript.txt, transcript.srt e transcript.json. Use sempre que o usuário quiser o texto de um vídeo ou áudio — "transcreve isso", "o que ele fala nesse vídeo", "gera a legenda", "passa pra texto" — e como etapa final do pipeline depois do download e da extração de áudio. Roda offline na GPU, sem enviar áudio para lugar nenhum.
---

# Transcrever

O trabalho é do `scripts/transcribe.py`. Ele corta o áudio nos silêncios, sobe um
`llama-server` uma única vez e transcreve chunk a chunk.

## Como invocar

```bash
uv run python scripts/transcribe.py "<pasta do vídeo>"
```

O argumento é a pasta que veio do download, com `audio.wav` dentro. Se o áudio ainda não
existir, o script diz para rodar a extração antes — nesse caso o passo que falhou é o
anterior, volte para ele.

Opções que existem por um motivo:

- `--model Qwen3-ASR-1.7B` — força o modelo maior. Por padrão a escolha é pela VRAM livre
  medida na hora, e o 1.7B só entra quando há uns 3,1 GB livres. Forçar num momento de pouca
  memória faz o servidor morrer ao subir.
- `--target 15` — chunks menores dão legendas mais granulares. Aumente para 60 ou mais se o
  que importa é o texto corrido, não a sincronia.
- `--force` — transcreve de novo por cima de uma transcrição existente.

## O que ele produz

Três arquivos na mesma pasta, três vistas do mesmo resultado:

- **`transcript.txt`** — texto com marcas de tempo por bloco, para ler ou colar
- **`transcript.srt`** — legenda, para navegar o vídeo
- **`transcript.json`** — segmentos com início e fim, para processar depois

## Limites que valem dizer ao usuário antes que ele descubra sozinho

**Os timestamps têm granularidade de bloco, não de palavra.** Cada legenda cobre uns 30 s.
Serve muito bem para achar onde um assunto aparece; não serve para legendar vídeo
profissionalmente. O Qwen3 no llama.cpp não produz timestamps próprios, e o alinhador do Qwen
não existe em formato GGUF — daí o limite.

**O estilo varia entre blocos.** Um trecho pode escrever "1784" e o seguinte "mil setecentos
e oitenta e quatro"; o mesmo vale para porcentagens. Cada bloco é uma chamada independente e
o modelo não mantém convenção entre elas. Já testamos pedir o formato no prompt: ele ignora,
porque é um modelo de reconhecimento de fala e não de instrução.

**A saída não é reproduzível palavra por palavra.** Rodar duas vezes pode trocar uma palavra
aqui ou ali. Por isso o `metadata.json` registra modelo, quantização e parâmetros usados — é
o que permite saber depois como um texto foi gerado.

## Se algo der errado

O servidor morrer ao subir quase sempre é falta de VRAM. Confira quanto havia livre (o script
registra isso em stderr) e deixe a escolha automática trabalhar, ou force o 0.6B.

O script derruba o servidor mesmo quando falha. Se ainda assim sobrar um processo, ele segura
a GPU inteira e a execução seguinte não sobe — vale conferir antes de culpar o modelo.

## Quanto tempo leva

Cerca de 14× mais rápido que o tempo real no modelo 0.6B: 10 minutos de áudio levam uns 40
segundos. Vídeos longos escalam de forma linear, porque o custo é por bloco.
