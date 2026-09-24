# Roadmap

**Current Milestone:** nenhum em andamento — M1 e M2 entregues
**Status:** M1 e M2 completos. YouTube e Instagram validados contra conteúdo real — F1 concluído em 2026-09-21; M1 fechado em 2026-09-23: link do YouTube entra, pasta com vídeo e transcrição sai

---

## Modelo de skills

Cada capacidade vira uma skill do Claude Code. A natureza da skill é escolhida pelo que a etapa realmente exige:

| Natureza | Quando | Forma |
|---|---|---|
| **Determinística** | A etapa tem uma resposta certa e repetível | SKILL.md fino + script Python/shell que faz o trabalho; o modelo apenas invoca e lê o resultado |
| **Híbrida** | Núcleo repetível, mas a configuração depende do contexto | Script determinístico + julgamento do modelo sobre parâmetros (modelo Whisper, idioma, qualidade) e sobre recuperação de erro |
| **Não determinística** | Não há caminho único; depende de julgamento | Instruções no SKILL.md; o modelo decide a sequência, invocando as outras skills |

---

## M1 — Pipeline YouTube ponta a ponta

**Goal:** Dado um link público do YouTube, uma única invocação produz `downloads/<data>-<slug>/` com vídeo, áudio, as três transcrições e `metadata.json`.
**Target:** Fluxo verificado com um vídeo curto (<5 min) e um longo (>30 min).

### Features

**F1 — Fundação do projeto** - COMPLETE

- Estrutura de diretórios (`scripts/`, `.claude/skills/`, `downloads/`)
- Ambiente Python gerenciado por `uv` com `pyproject.toml`
- Convenções de código e contrato de saída dos scripts (JSON em stdout, erros em stderr, exit codes)
- `.gitignore` e inicialização do repositório git

**F2 — Skill de download (determinística)** - COMPLETE

- Recebe URL, valida e identifica a plataforma
- Baixa o melhor vídeo disponível via `yt-dlp` para uma pasta nomeada por data + slug do título
- Grava `metadata.json` com URL, título, canal/autor, duração, data de publicação e data do download
- Reporta erro de forma legível quando o link é privado, removido ou bloqueado por região

**F3 — Skill de extração de áudio (determinística)** - COMPLETE

- Extrai o áudio do vídeo baixado via `ffmpeg` em WAV 16 kHz mono PCM
- Reaproveita o arquivo existente se já tiver sido extraído
- Falha explicitamente quando o vídeo não tem faixa de áudio

**F4 — Skill de transcrição (híbrida)** - COMPLETE

Dois engines intercambiáveis atrás de uma interface só. A escolha entre eles é o julgamento que justifica a skill ser híbrida:

- **Qwen3-ASR (padrão)** via `llama-mtmd-cli` do llama.cpp — melhor em áudio com música de fundo e ruído, que é o caso típico de Reels e vídeos da internet
- **faster-whisper (alternativa)** — quando a prioridade for legenda sincronizada de material limpo, por causa dos timestamps nativos

Capacidades:

- Mede a VRAM livre em tempo de execução e escolhe entre 1.7B e 0.6B a partir dela (ver AD-006)
- Roda sem `-ngl` fixo, deixando o llama.cpp ajustar o offload à memória livre (ver AD-007)
- Define `-c` de acordo com a duração do chunk — o limite do áudio longo é o contexto, não a VRAM (ver L-006)
- Chunking obrigatório em janelas de ~3 min com sobreposição: além de evitar o estouro de contexto, é ~4× mais rápido que um bloco longo (ver L-007)
- Detecção automática de idioma, sobrescrevível pelo usuário
- Escreve `transcript.txt`, `transcript.srt` e `transcript.json`, e registra no `metadata.json` engine, modelo, quantização e parâmetros usados (a saída não é bit-determinística, ver L-008)
- No caminho Qwen3, gera os timestamps do `.srt` via `Qwen3-ForcedAligner-0.6B` (janelas de até 5 min)

**F2 — nota de implementação descoberta na validação:** o download precisa usar o `yt-dlp` do projeto (não o do sistema), passar `--js-runtimes node` e baixar o arquivo completo — `--download-sections` é rejeitado com 403 pelo YouTube.

**F5 — Skill orquestradora (não determinística)** - COMPLETE

- Ponto de entrada em linguagem natural: "transcreve esse link"
- Encadeia download → extração → transcrição, retomando de onde parou se a pasta já existir parcialmente
- Decide o que fazer diante de falhas parciais (repetir, ajustar modelo, reportar ao usuário)
- Resume ao final o que foi produzido e onde está

---

## M2 — Instagram

**Goal:** O mesmo fluxo do M1 funciona com links públicos de Reels e posts do Instagram.

### Features

**F6 — Suporte a Instagram** - COMPLETE

- Extensão da skill de download para URLs do Instagram — feito
- Normalização de metadados: o nome da pasta desce por título, legenda, autor e id até achar algo que sobreviva à transliteração — feito
- Tratamento explícito de rate limit, exigência de login e extractor quebrado — feito
- Carrossel: um post mistura fotos e vídeos, e o yt-dlp aborta o conjunto ao esbarrar numa foto. As posições com vídeo são escolhidas de antemão, e cada uma vira uma pasta — feito
- Tolerância a item defeituoso: um vídeo mudo no meio do post não derruba os outros — feito
- Validado em 2026-09-24 contra um post real de 11 itens (7 vídeos, 1 sem faixa de áudio, nenhum com fala)

---

## Future Considerations

- Diarização de falantes (`pyannote.audio`) com marcação `[SPEAKER_XX]`
- Processamento em lote de várias URLs
- Fallback para API de transcrição em vídeos longos ou quando a GPU estiver ocupada
- Pós-processamento: resumo, extração de tópicos, correção de pontuação
- Outras plataformas (TikTok, Twitter/X, Vimeo)
- Suporte a conteúdo autenticado via cookies do navegador
