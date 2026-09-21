# Audio Transcriber

**Vision:** Ferramenta operada por skills do Claude Code que, a partir de uma URL de YouTube ou Instagram, baixa o vídeo, transcreve o áudio localmente e salva a transcrição ao lado do vídeo.
**For:** Uso pessoal do Salmo — capturar conteúdo em vídeo como texto pesquisável, sem depender de serviços externos.
**Solves:** Hoje o processo é manual e improvisado (scripts soltos, venv gigante, sem estrutura). Não há um caminho único e repetível de "URL → vídeo + transcrição organizados em disco".

## Goals

- Dado um link público de YouTube ou Instagram, produzir vídeo + transcrição em uma única invocação, sem intervenção manual entre as etapas.
- Transcrição 100% local (GPU RTX 3050), sem custo por minuto e sem enviar áudio para terceiros.
- Toda a capacidade exposta como skills do Claude Code, invocáveis em linguagem natural ("transcreve esse link").
- Saída organizada e determinística: uma pasta por vídeo, com nomes previsíveis e `metadata.json`.

## Tech Stack

**Core:**

- Linguagem: Python 3.12
- Gerenciador de ambiente/deps: uv (0.9.5)
- Runtime de skills: Claude Code (`.claude/skills/`)

**Key dependencies:**

- `yt-dlp` — download de YouTube e Instagram. **Dependência do projeto, nunca a do sistema**: versões com poucos meses quebram com 403 no YouTube (ver L-002).
- Node.js 24 — runtime JavaScript exigido pelo yt-dlp para extração completa do YouTube (`--js-runtimes node`, ver L-003)
- `ffmpeg` 6.1.1 — extração e normalização de áudio
- `llama.cpp` (build CUDA pré-compilado, binário `llama-mtmd-cli`) — runtime do Qwen3-ASR em GGUF, sem PyTorch
- `Qwen3-ASR` (Apache 2.0, GGUF oficial de `ggml-org`) — engine de transcrição padrão
- `faster-whisper` — engine alternativo, quando a prioridade for legenda com timestamps nativos

## Scope

**v1 includes:**

- Download de vídeo a partir de URL pública do YouTube
- Download de vídeo a partir de URL pública do Instagram (Reels/posts)
- Extração de áudio em formato adequado para ASR (WAV 16 kHz mono)
- Transcrição local com dois engines intercambiáveis (Qwen3-ASR como padrão, faster-whisper como alternativa), escolhidos conforme o áudio e a necessidade de timestamps
- Saída em `downloads/<data>-<titulo-slug>/` com: vídeo, áudio, `transcript.txt`, `transcript.srt`, `transcript.json`, `metadata.json`
- Skills que orquestram o fluxo ponta a ponta e também cada etapa isoladamente

**Explicitly out of scope:**

- Diarização de falantes (quem fala o quê) — adiada para v2
- Conteúdo que exige autenticação (stories, contas privadas, vídeos restritos)
- Transcrição via API paga (OpenAI, Deepgram) como fallback
- Interface gráfica ou web
- Tradução, resumo ou qualquer pós-processamento do texto
- Processamento em lote de múltiplas URLs
- Suporte a outras plataformas (TikTok, Twitter/X, Vimeo)

## Constraints

- **Técnico:** A GPU tem 4 GB nominais, mas o Windows já consome de 1,0 a 2,0 GB de forma variável (medido: 1039–1978 MiB sem nenhum processo CUDA no WSL). O orçamento real de VRAM precisa ser medido em tempo de execução, não assumido.
- **Técnico:** O download do Instagram é frágil por natureza — o yt-dlp quebra com mudanças da plataforma e sofre rate limit. Falhas nessa origem são esperadas e devem ser reportadas com clareza, não mascaradas.
- **Técnico:** O consumo de VRAM é dominado pelo encoder de áudio, não pelos pesos: 180 s de áudio no modelo de 0.6B levaram o pico a 3653 MiB. Chunking do áudio é obrigatório, com a janela dimensionada pela VRAM livre.
- **Técnico:** O Qwen3-ASR não produz timestamps de segmento nativos. Gerar `.srt` com ele exige o `Qwen3-ForcedAligner-0.6B`, que alinha em janelas de até 5 minutos. Com faster-whisper os timestamps saem de graça.
- **Processo:** As skills devem ser criadas usando o `skill-creator` do Claude, não escritas à mão.
- **Legal:** Uso pessoal, apenas conteúdo público. A ferramenta não contorna DRM nem autenticação.
