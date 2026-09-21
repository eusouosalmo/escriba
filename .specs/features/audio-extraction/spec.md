# F3 — Skill de extração de áudio

**Natureza:** determinística. `ffmpeg` com parâmetros fixos; não há o que decidir.

## Requisitos

| ID | Requisito | Verificação |
|---|---|---|
| R1 | Recebe a pasta do vídeo e extrai o áudio para `audio.wav` dentro dela | Rodar sobre a pasta baixada no F2 |
| R2 | O WAV sai em 16 kHz, mono, PCM 16 bits — o formato que o ASR espera | `ffprobe` no arquivo gerado |
| R3 | Não reextrai o que já existe; devolve o caminho existente | Rodar duas vezes e comparar o mtime |
| R4 | Vídeo sem faixa de áudio falha com mensagem clara, não com erro do ffmpeg | Gerar um vídeo mudo e rodar |
| R5 | Ausência do ffmpeg falha com `ENVIRONMENT` e diz como instalar | Simular PATH sem ffmpeg |
| R6 | Pasta inexistente ou sem vídeo falha com `USAGE` | Apontar para uma pasta vazia |
| R7 | Registra no `metadata.json` o arquivo de áudio gerado e sua duração | Ler o JSON |
| R8 | Obedece ao contrato de I/O | Teste de linha de comando |

## Fora de escopo

- Normalização de volume, remoção de ruído ou separação de voz
- Formatos além do WAV exigido pelo ASR
- Extrair de arquivo avulso fora da estrutura de pastas do projeto
