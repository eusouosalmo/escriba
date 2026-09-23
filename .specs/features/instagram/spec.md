# F6 — Suporte a Instagram

**Natureza:** determinística, como o resto do download. A diferença está nos dados que a origem fornece — e sobretudo nos que ela não fornece.

## O que muda em relação ao YouTube

O Instagram não entrega título nem canal do mesmo jeito. O que existe é a legenda do post, que pode ser longa, vazia, ou só emoji. Também não há garantia de data de publicação em todo tipo de conteúdo. Como o nome da pasta é montado a partir de data e título, ele precisa continuar previsível quando nenhum dos dois vier.

## Requisitos

| ID | Requisito | Verificação |
|---|---|---|
| R1 | Aceita URLs de Reel e de post do Instagram | Rodar com um link real de cada |
| R2 | Sem título, deriva o nome da pasta da legenda; sem legenda, usa o autor e o id | Teste do nome com metadados ausentes |
| R3 | Legenda longa vira um slug curto e legível, não um nome de pasta gigante | Teste com legenda de várias linhas |
| R4 | O `metadata.json` registra `platform: instagram` e o autor, quando houver | Ler o JSON |
| R5 | Exigência de login falha com mensagem clara de escopo, não com erro cru | Rodar com um link privado |
| R6 | Limite de taxa é reconhecido e a dica diz para esperar, não para repetir | Mapear a mensagem do extractor |
| R7 | O pipeline inteiro funciona com um link do Instagram | Rodar ponta a ponta |

## Fora de escopo

- Stories e conteúdo que exija autenticação
- Perfis inteiros ou carrosséis com vários vídeos
- Contornar bloqueio ou rate limit

## Risco declarado

Esta é a parte mais frágil do projeto, e o motivo de ela viver num milestone próprio: o Instagram muda com frequência e quebra o extractor sem aviso. Falhas aqui devem ser reportadas com clareza — inclusive a possibilidade de simplesmente ter parado de funcionar — em vez de disfarçadas de erro do usuário.
