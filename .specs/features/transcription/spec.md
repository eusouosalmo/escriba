# F4 — Skill de transcrição

**Natureza:** híbrida. O núcleo é determinístico, mas escolher o modelo depende da VRAM livre no momento, que não está sob nosso controle.

## Requisitos

| ID | Requisito | Verificação |
|---|---|---|
| R1 | Recebe a pasta do vídeo e transcreve o `audio.wav` que está nela | Rodar sobre a pasta do F3 |
| R2 | Corta o áudio nos silêncios (`ffmpeg silencedetect`), não em blocos fixos, para não partir frases | Conferir os cortes contra os silêncios detectados |
| R3 | Agrupa trechos até um alvo de duração, com corte duro só quando um trecho sozinho excede o máximo | Teste do agrupamento |
| R4 | Sobe o `llama-server` uma vez e o reaproveita entre os chunks | O tempo por chunk não pode incluir carga de modelo |
| R5 | Escolhe o modelo pela VRAM livre medida na hora: 1.7B quando couber, 0.6B quando não | Teste do seletor com valores simulados |
| R6 | Escreve `transcript.txt`, `transcript.srt` e `transcript.json` | Conferir os três arquivos |
| R7 | Os timestamps vêm das fronteiras reais dos chunks, e o `.srt` é válido | Conferir a numeração e o formato dos tempos |
| R8 | Remove repetições e alucinações do ASR | Teste com texto repetitivo |
| R9 | Registra no `metadata.json` engine, modelo, quantização e parâmetros (a saída não é bit-determinística, ver L-008) | Ler o JSON |
| R10 | Derruba o servidor ao terminar, inclusive em caso de erro ou interrupção | Conferir que nada fica órfão |
| R11 | Obedece ao contrato de I/O | Teste de linha de comando |

## Fora de escopo

- Backend faster-whisper — exigiria 2-3 GB de dependências e só se paga quando houver necessidade real de legenda sincronizada
- Timestamps por palavra — o Qwen3 via llama.cpp não os produz, e o ForcedAligner não existe em GGUF
- Diarização

## Decisões de projeto, com a medição que as sustenta

- **VAD por `silencedetect`, sem dependência nova**: no áudio de teste deu mediana de 7,2 s entre cortes e só 4 trechos acima de 30 s em 10 min. Música contínua reduz a detecção — de 9,8 s a 71,8 s não houve silêncio algum — e é para isso que existe o corte duro no máximo.
- **Servidor em vez de CLI**: o `llama-mtmd-cli` recarrega o modelo a cada chamada, o que dominaria o tempo com dezenas de chunks. Medido via servidor: 30 s de áudio transcritos em 2,1 s com o modelo já carregado.
- **O `.srt` tem granularidade de chunk**, não de palavra. Serve para navegar o conteúdo, não para legendar vídeo profissionalmente. É o limite do que dá para fazer sem trazer PyTorch de volta.
