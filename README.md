# audio-transcriber

Baixa um vídeo do YouTube ou do Instagram, transcreve o áudio localmente e guarda tudo junto — vídeo, áudio e transcrição na mesma pasta.

Operado por conversa, através de [skills do Claude Code](https://docs.claude.com/en/docs/claude-code/skills). Você manda o link, a ferramenta faz o resto:

```
"transcreve esse link: https://youtube.com/watch?v=..."
```

> **Status:** em construção. A arquitetura e o engine de transcrição estão definidos e validados na máquina-alvo; as skills ainda não foram implementadas. Veja o [roadmap](.specs/project/ROADMAP.md).

---

## Por que existe

Transcrever um vídeo à mão é uma sequência chata de passos manuais: achar o downloader que ainda funciona, extrair o áudio no formato certo, lembrar qual modelo cabe na GPU, e no fim ter arquivos espalhados sem saber de qual vídeo vieram. Aqui isso é um comando só, e a saída é organizada por construção.

Tudo roda **localmente**. Nenhum áudio é enviado para serviço de terceiros, e não há custo por minuto transcrito.

## Como funciona

```
URL ──▶ download ──▶ extração de áudio ──▶ transcrição ──▶ downloads/<data>-<titulo>/
        (yt-dlp)      (ffmpeg, WAV 16k)     (Qwen3-ASR)        ├── video.mp4
                                                                ├── audio.wav
                                                                ├── transcript.txt
                                                                ├── transcript.srt
                                                                ├── transcript.json
                                                                └── metadata.json
```

Cada etapa é uma skill. A natureza de cada uma segue o que ela realmente exige:

| Skill | Natureza | Por quê |
|---|---|---|
| Download | determinística | Dada uma URL, existe um resultado certo. Script faz, modelo só invoca. |
| Extração de áudio | determinística | `ffmpeg` com parâmetros fixos. Não há o que decidir. |
| Transcrição | **híbrida** | O núcleo é um script, mas escolher engine, modelo e janela depende do áudio e da VRAM livre no momento. |
| Orquestração | **não determinística** | Encadear, retomar o que já foi feito e reagir a falha parcial é julgamento, não roteiro. |

## Engine de transcrição

O padrão é o **[Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)** (Alibaba, Apache 2.0), rodando em GGUF sobre o [llama.cpp](https://github.com/ggml-org/llama.cpp) — sem PyTorch, sem CUDA toolkit, sem venv de vários GB.

A escolha não foi por benchmark de vitrine: o Qwen3-ASR é treinado explicitamente para fala sobre música e com relação sinal-ruído baixa, que é o áudio típico de vídeo de internet, onde o Whisper tende a alucinar letra de música. O **faster-whisper** fica disponível como alternativa para quando a prioridade for legenda sincronizada, já que entrega timestamps nativos.

### Medições na máquina-alvo

RTX 3050 Laptop (4 GB nominais) sob WSL2, com narração em português brasileiro sobre trilha sonora:

| Modelo | Áudio | Tempo | Velocidade | Pico de VRAM |
|---|---|---|---|---|
| Qwen3-ASR-0.6B Q8_0 | 3 min | 10,2 s | 17,6× tempo real | 3653 MiB |
| Qwen3-ASR-1.7B Q8_0 | 3 min | 21,6 s | 8,3× tempo real | 3894 MiB |
| Qwen3-ASR-1.7B Q8_0 | 10 min | 294,9 s | 2,05× tempo real | 3848 MiB |

Três coisas que essas medições ensinaram, e que estão embutidas no design:

- **A VRAM livre não é a VRAM da placa.** O Windows consome de 750 MiB a 2 GB da GPU do notebook, variando com o que está aberto. O modelo é escolhido medindo o espaço livre na hora, não pelo total da placa.
- **O limite do áudio longo é o context window, não a memória.** Dez minutos falham com o contexto padrão enquanto a VRAM está folgada — ampliar o contexto resolve, reduzir o modelo não.
- **Chunking é performance, não só segurança.** A velocidade cai de 8,3× para 2,05× conforme o bloco cresce. Processar em janelas de ~3 min é cerca de 4× mais rápido que mandar o áudio inteiro.

## Requisitos

- Python 3.12+ e [uv](https://docs.astral.sh/uv/)
- ffmpeg
- Node.js — o `yt-dlp` passou a exigir um runtime JavaScript para extração completa do YouTube
- GPU NVIDIA com CUDA (opcional; sem ela a transcrição roda em CPU, bem mais devagar)
- Claude Code, para operar as skills

Uma nota que vale o aviso: **o `yt-dlp` precisa estar atualizado**. Versões com poucos meses não degradam, elas simplesmente param de funcionar com `403 Forbidden` no YouTube. Por isso ele é dependência declarada do projeto, e não a versão instalada no sistema.

## Escopo

**Entra:** YouTube e Instagram públicos, download, extração, transcrição com timestamps, saída em `.txt`, `.srt` e `.json`.

**Não entra (por ora):** diarização de falantes, conteúdo que exija login, transcrição via API paga, interface gráfica, processamento em lote, tradução ou resumo.

## Documentação

O projeto é planejado com [spec-driven development](https://github.com/techleadsclub). Os documentos vivos estão em `.specs/`:

- [`PROJECT.md`](.specs/project/PROJECT.md) — visão, stack e fronteiras de escopo
- [`ROADMAP.md`](.specs/project/ROADMAP.md) — milestones e features
- [`STATE.md`](.specs/project/STATE.md) — decisões arquiteturais, lições aprendidas e pendências

Se você quer entender *por que* o projeto é do jeito que é, o `STATE.md` é o documento mais útil: cada decisão está registrada com o trade-off que ela custou.

## Licença

MIT — veja [LICENSE](LICENSE).
