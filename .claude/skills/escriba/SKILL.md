---
name: escriba
description: Pega um link de vídeo do YouTube ou do Instagram e entrega o vídeo baixado com a transcrição ao lado, fazendo download, extração de áudio e transcrição local numa tacada só. Use sempre que o usuário mandar uma URL de vídeo querendo o conteúdo em texto — "escriba, pega esse link", "transcreve esse vídeo", "o que ele fala aqui", "quero o texto disso" — inclusive quando ele apenas colar a URL sem dizer o que quer. É o ponto de entrada natural do projeto; as skills de download, extração e transcrição existem para quando só uma etapa é necessária.
---

# escriba

Junta as três etapas do projeto: baixar, extrair o áudio, transcrever. O caminho comum é uma
linha só; o julgamento fica para quando algo sai do esperado.

## O caminho comum

```bash
uv run python scripts/pipeline.py "<URL>"
```

Ao final, um JSON com a pasta, o título, a duração, o idioma detectado, o modelo usado e os
caminhos do vídeo, do áudio e das três transcrições.

Opções, quando o pedido for específico: `--model Qwen3-ASR-1.7B` para forçar o modelo maior,
`--target 15` para blocos de legenda menores, `--max-height 0` para baixar em qualidade
máxima, `--force` para refazer tudo por cima.

## Rodar de novo é a forma de retomar

Cada etapa reconhece o próprio trabalho feito e devolve `reused: true` em vez de repeti-lo.
Se uma execução foi interrompida — download pela metade, transcrição incompleta — basta
chamar o pipeline outra vez com a mesma URL: o que já existe responde em segundos e só o que
falta é executado.

Isso vale também quando o usuário manda um link que ele já processou antes. A resposta vem
em poucos segundos e o campo `reused_stages` diz o que foi aproveitado. Vale mencionar, para
ele não achar que a ferramenta ignorou o pedido.

## Quando uma etapa falha

O pipeline para na etapa que falhou e devolve `stage` dizendo qual foi, preservando o código
de saída e a dica dela. Trate essa dica como a melhor informação disponível — ela vem de quem
sabe o que aconteceu.

O que vale fazer em cada caso:

**Código 2, entrada inválida.** A URL não é suportada ou está malformada. Diga o limite ao
usuário: YouTube e Instagram, uma URL por vez, só conteúdo público.

**Código 3, ambiente.** Falta uma ferramenta. Siga a dica — costuma ser `uv sync` ou instalar
o ffmpeg — e só então tente de novo.

**Código 1 no download.** Vídeo privado, removido ou bloqueado é escopo, não defeito: relate
e pare. Se a dica falar em 403, o problema é o yt-dlp desatualizado, não o vídeo. Se falar em
limite de taxa, **não repita a chamada** — insistir piora a situação; espere.

No Instagram há uma causa a mais: o extractor quebra quando a plataforma muda. Se a dica
sugerir atualizar o yt-dlp, é isso — e vale dizer ao usuário que o link dele provavelmente
está certo.

**Código 1 na transcrição.** Quase sempre é VRAM. O script registra em stderr quanto havia
livre; se o usuário forçou o modelo grande num momento apertado, refaça deixando a escolha
automática. Se sobrou algum servidor de execução anterior segurando a GPU, ele precisa cair
antes.

Repetir automaticamente uma etapa que falhou não é o comportamento padrão. Duas das causas
mais comuns — limite de taxa e falta de memória — pioram com insistência.

## O que contar ao usuário no fim

Título, duração e onde as coisas ficaram. O caminho da pasta é o que ele vai abrir.

Se ele pediu a transcrição para ler, mostre um trecho do começo em vez de só apontar o
arquivo — é o que ele queria de fato.

Dois limites que vale declarar quando forem relevantes ao pedido: as legendas têm
granularidade de bloco (uns 30 s cada), boas para navegar e não para legendar vídeo
profissionalmente; e o estilo pode variar entre blocos, com um trecho escrevendo "1784" e
outro "mil setecentos e oitenta e quatro". Nenhum dos dois é defeito de execução — são
limites do modelo local, explicados na skill `transcription`.

## Quando usar as skills individuais

Se o usuário quer só baixar, ou só o áudio, ou transcrever algo que já está em disco, chame
a skill correspondente (`video-download`, `audio-extraction`, `transcription`) em vez do
pipeline. Ele é o atalho do caso completo, não uma obrigação.
