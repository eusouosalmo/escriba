# State

**Last Updated:** 2026-09-21
**Current Work:** F1, F2 e F3 concluídos e publicado em github.com/eusouosalmo/escriba (privado). Projeto renomeado de audio-transcriber para escriba em 2026-09-21. Próximo: F4 — skill de transcrição, o núcleo do projeto.

---

## Recent Decisions (Last 60 days)

### AD-001: Skills do Claude Code + scripts Python determinísticos (2026-09-19)

**Decision:** Cada capacidade é uma skill em `.claude/skills/`, com o trabalho pesado em scripts Python sob `scripts/`. As skills são criadas com o `skill-creator` do Claude, não escritas à mão.
**Reason:** Mantém o comportamento repetível nos scripts (testáveis, versionáveis) e reserva o julgamento do modelo para o que é realmente ambíguo. O uso é conversacional, que é como o Salmo quer operar.
**Trade-off:** Não funciona fora do Claude Code — não há CLI pública como contrato de primeira classe.
**Impact:** Os scripts precisam de um contrato de I/O estável (argumentos explícitos, JSON em stdout, exit codes) para que as skills sejam finas e confiáveis.

### AD-002: Qwen3-ASR via llama.cpp como engine padrão, faster-whisper como alternativa (2026-09-19, revisada)

**Decision:** Transcrição local com dois engines atrás de uma interface só. Padrão: `Qwen3-ASR-1.7B` Q8_0 (GGUF oficial de `ggml-org`, Apache 2.0) rodando no `llama-mtmd-cli` do llama.cpp. Alternativa: `faster-whisper`, quando a prioridade for legenda sincronizada.
**Reason:** Validado na máquina em 2026-09-19 com áudio real em PT-BR com trilha sonora. O Qwen3-ASR foi treinado explicitamente para áudio com música e SNR baixo — o caso típico de Reels. Roda em C++ sem PyTorch, o que evita repetir o venv de 8 GB do projeto anterior. A versão original desta decisão previa faster-whisper como engine único; foi substituída após a pesquisa e a validação.
**Trade-off:** O Qwen3-ASR não dá timestamps de segmento nativos — o `.srt` exige o `Qwen3-ForcedAligner-0.6B` em janelas de até 5 min. É exatamente aí que o faster-whisper continua valendo.
**Impact:** A skill F4 precisa de dois backends plugáveis e da escolha entre eles como julgamento explícito.

### AD-006: Modelo 1.7B como padrão, 0.6B como fallback por VRAM (2026-09-19)

**Decision:** Usar `Qwen3-ASR-1.7B` Q8_0 por padrão e cair para o `0.6B` Q8_0 quando a VRAM livre não comportar o maior.
**Reason:** Diferença de qualidade medida no mesmo áudio de 3 min: o 1.7B escreveu "John Michell" (grafia correta), "seria desacelerada" (o 0.6B inverteu o sentido para "acelerada"), "descrevem" e "acendesse ela"; o 0.6B errou os quatro e truncou a última frase. O 0.6B, ainda assim, é bom e roda a 17,6× tempo real.
**Trade-off:** O 1.7B usa ~3,0 GB e só cabe quando o Windows está consumindo pouca VRAM. Não é garantido.
**Impact:** A skill precisa medir a VRAM livre antes de escolher, e o 0.6B precisa ser um caminho testado, não teórico.

### AD-008: Vídeo limitado a 1080p por padrão (2026-09-21)

**Decision:** O download usa teto de 1080p, com `--max-height 0` para quem quiser a melhor qualidade disponível.
**Reason:** Medido no vídeo de teste de 10 min: sem teto, 481 MB em 7 minutos; com teto, 71 MB em 72 segundos. O material existe para ser transcrito e consultado, não arquivado em qualidade máxima.
**Trade-off:** Quem quiser guardar o vídeo em 4K precisa pedir explicitamente.
**Impact:** O teto fica registrado no `metadata.json`, para saber depois em que qualidade cada item foi salvo.

### AD-007: Rodar sem `-ngl` fixo, deixando o llama.cpp auto-ajustar o offload (2026-09-19)

**Decision:** Não passar `-ngl`; deixar o `common_fit_params` do llama.cpp decidir quantas camadas cabem na VRAM livre.
**Reason:** Com `-ngl 99` o llama.cpp emite `failed to fit params to free device memory ... abort` e tenta forçar tudo na GPU, o que só funcionou porque o Windows estava usando pouca VRAM naquele momento. No modo automático ele se adapta à memória livre real, que varia de 750 a 2000 MiB entre execuções.
**Trade-off:** ~29% mais lento no teste de 3 min (27,9 s contra 21,6 s).
**Impact:** Robustez vale mais que o pico de velocidade, porque a VRAM livre não está sob nosso controle.

### AD-003: Diarização fora do v1 (2026-09-19)

**Decision:** v1 entrega apenas texto com timestamps, sem identificar falantes.
**Reason:** `pyannote.audio` exige token HuggingFace, mais VRAM e aumenta bastante a superfície de falha, sem ser necessário para o objetivo principal.
**Trade-off:** Transcrições de reunião ficam menos úteis que a saída do script antigo, que já marcava `SPEAKER_XX`.
**Impact:** Está no roadmap como consideração futura.

### AD-004: Uma pasta por vídeo, três formatos de transcrição (2026-09-19)

**Decision:** Saída em `downloads/<data>-<titulo-slug>/` com vídeo, áudio, `transcript.txt`, `transcript.srt`, `transcript.json` e `metadata.json`.
**Reason:** Agrupar por vídeo facilita achar e apagar em bloco. Os três formatos são views baratas do mesmo resultado da transcrição.
**Trade-off:** Mais arquivos por vídeo do que o mínimo necessário.
**Impact:** O caminho da pasta é o identificador que circula entre todas as skills do pipeline.

### AD-005: Apenas conteúdo público, sem autenticação (2026-09-19)

**Decision:** v1 não lida com cookies, login ou conteúdo restrito.
**Reason:** Mantém o escopo enxuto e evita a parte mais frágil e mais sujeita a bloqueio do yt-dlp.
**Trade-off:** Stories e contas privadas ficam de fora.
**Impact:** Falhas por exigência de login devem ser reportadas claramente, não contornadas.

---

## Active Blockers

Nenhum.

---

## Lessons Learned

### L-001: O projeto anterior acumulou 8 GB sem estrutura (2026-09-19)

**Context:** O diretório continha um `venv/` de 7,7 GB, `.mypy_cache` de 232 MB, um WAV de 78 MB e scripts soltos, sem git.
**Problem:** Sem repositório, sem `.gitignore` e sem separação entre código e artefatos, o projeto ficou impossível de versionar ou retomar.
**Solution:** Zerado por decisão do usuário; o novo projeto começa com git, `.gitignore` e `uv` desde a primeira feature.
**Prevents:** Artefatos pesados (`venv/`, `downloads/`, caches, mídia) entrarem no repositório ou se misturarem ao código.

### L-002: yt-dlp do sistema está quebrado para YouTube; a versão precisa ser do projeto (2026-09-19)

**Context:** O `yt-dlp` 2026.03.17 instalado no sistema retornou `HTTP Error 403: Forbidden` em qualquer download do YouTube.
**Problem:** O YouTube muda a extração com frequência e versões com mais de alguns meses param de funcionar por completo — não degradam, quebram.
**Solution:** Rodar `yt-dlp` 2026.08.19 via `uvx yt-dlp@latest` resolveu na hora.
**Prevents:** Depender do binário do sistema. O yt-dlp deve ser dependência declarada do projeto, com atualização fácil e mensagem de erro que oriente atualizar quando der 403.

### L-003: yt-dlp agora exige um runtime JavaScript para o YouTube (2026-09-19)

**Context:** O download emitiu `No supported JavaScript runtime could be found. Only deno is enabled by default`.
**Problem:** Sem runtime JS, a extração do YouTube é degradada e alguns formatos ficam indisponíveis.
**Solution:** A máquina tem Node 24; basta passar `--js-runtimes node`. Deno não está instalado.
**Prevents:** Downloads silenciosamente piores ou falhas intermitentes de formato.

### L-004: `--download-sections` não funciona no YouTube (2026-09-19)

**Context:** Tentativa de baixar só os primeiros 180 s com `--download-sections` resultou em `403 Forbidden` vindo do ffmpeg.
**Problem:** Essa opção faz o ffmpeg pedir intervalos direto ao CDN do Google, que rejeita a requisição.
**Solution:** Baixar o arquivo completo com o downloader nativo do yt-dlp e cortar localmente com ffmpeg.
**Prevents:** Desenhar a skill de download em cima de uma opção que não funciona para a origem principal.

### L-005: A GPU tem ~2 GB livres, não 4 GB (2026-09-19)

**Context:** `nvidia-smi` mostra 1978 MiB de 4096 MiB já ocupados sem nenhum processo CUDA no WSL.
**Problem:** É o Windows consumindo a VRAM da GPU do notebook. O orçamento real de VRAM é menos da metade do nominal, e varia conforme o que estiver aberto no Windows.
**Solution:** Dimensionar os modelos pelo espaço livre medido em tempo de execução, não pelo total da placa.
**Prevents:** Escolher modelo por tamanho nominal e tomar OOM em uso real.

### L-006: O limite do áudio longo é o context window, não a VRAM (2026-09-19)

**Context:** Áudio de 10 min no 1.7B falhou com `decode: failed to find a memory slot for batch of size 104`, com pico de VRAM em apenas 3637 MiB.
**Problem:** É fácil ler a falha como falta de memória de GPU e reduzir o modelo sem necessidade.
**Solution:** `-c 16384` resolveu; os 10 min transcreveram por completo com pico de 3848 MiB.
**Prevents:** Diagnosticar mal a falha de áudio longo e degradar o modelo à toa.

### L-007: Chunking deixa a transcrição ~4× mais rápida, além de evitar o limite de contexto (2026-09-19)

**Context:** O mesmo modelo transcreveu 180 s em 21,6 s (8,3× tempo real) e 604 s em 294,9 s (2,05× tempo real).
**Problem:** O custo de atenção cresce mais que linearmente com o contexto, então um bloco longo é desproporcionalmente lento.
**Solution:** Processar em janelas de ~3 min com sobreposição. Estimativa para os mesmos 10 min: ~73 s em vez de 295 s.
**Prevents:** Tratar chunking como mera proteção contra OOM e perder o ganho de velocidade.

### L-008: A transcrição não é bit-determinística entre configurações (2026-09-19)

**Context:** O mesmo modelo, no mesmo áudio, produziu "você vai ver a luz, essa lanterna" com `-ngl 99` e "a luz dessa lanterna" no modo auto-fit — a segunda está correta.
**Problem:** Mudar o offload muda o resultado numérico e, ocasionalmente, a palavra escolhida.
**Solution:** Tratar a transcrição como etapa não reproduzível bit a bit e registrar no `metadata.json` o engine, o modelo, a quantização e os parâmetros usados.
**Prevents:** Prometer determinismo que a skill não tem e perder a rastreabilidade de como um texto foi gerado.

### L-009: `uv run` cai para o binário do sistema em silêncio quando o venv quebra (2026-09-21)

**Context:** Ao renomear o diretório do projeto, o `.venv` quebrou (guarda caminhos absolutos). `uv run pytest` falhou explicitamente, mas `uv run yt-dlp --version` respondeu `2026.03.17` — a versão do sistema, justamente a que dá 403 no YouTube.
**Problem:** A falha é silenciosa e disfarçada: o comando funciona, só que com o binário errado. Seria diagnosticado como "o yt-dlp voltou a quebrar" em vez de "o ambiente está quebrado".
**Solution:** `rm -rf .venv && uv sync` restaura. Os scripts devem registrar a versão do yt-dlp que usaram no `metadata.json` e falhar com `ENVIRONMENT` quando ela for mais antiga que a mínima declarada.
**Prevents:** Perseguir um bug de download inexistente quando o problema é o ambiente.

---

## Quick Tasks Completed

| #   | Description                                      | Date       | Commit | Status  |
| --- | ------------------------------------------------ | ---------- | ------ | ------- |
| 001 | Zerar diretório do projeto anterior (8 GB removidos) | 2026-09-19 | —      | ✅ Done |

---

## Deferred Ideas

- [ ] Diarização de falantes com pyannote.audio — Captured during: inicialização
- [ ] Fallback para API de transcrição quando a GPU não der conta — Captured during: inicialização
- [ ] Processamento em lote de múltiplas URLs — Captured during: inicialização
- [ ] Resumo / extração de tópicos a partir da transcrição — Captured during: inicialização

---

## Todos

- [x] ~~Confirmar suporte a CUDA nesta máquina~~ — resolvido: binário CUDA 12.8 pré-compilado do llama.cpp (build b11056) roda na RTX 3050 sob WSL2 sem CUDA toolkit instalado
- [x] ~~Medir qual modelo cabe nos 4 GB~~ — resolvido: 1.7B Q8_0 usa ~3,0 GB e cabe quando o Windows está leve; 0.6B Q8_0 usa ~1,8 GB e sempre cabe
- [ ] Decidir onde o llama.cpp e os GGUF vão morar em definitivo (hoje estão no scratchpad e em `~/.cache/huggingface`, ~3,4 GB de modelos)
- [ ] Validar o `Qwen3-ForcedAligner-0.6B` na prática antes de prometer `.srt` pelo caminho Qwen3
- [ ] Testar a qualidade num Reel do Instagram de verdade (o teste foi com narração de YouTube sobre trilha sonora)

---

## Preferences

- Idioma de trabalho: Português (Brasil)
- Skills devem ser criadas via `skill-creator`, não escritas à mão
