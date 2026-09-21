# F2 — Skill de download

**Natureza:** determinística. Dada uma URL, existe um resultado certo; o script faz, a skill invoca e lê.

## Requisitos

| ID | Requisito | Verificação |
|---|---|---|
| R1 | Aceita URL de vídeo do YouTube e baixa a melhor qualidade disponível | Baixar um vídeo curto e conferir que o arquivo existe e toca |
| R2 | URL não suportada ou malformada falha com `USAGE` e mensagem clara | Passar `https://exemplo.com/x` e um texto qualquer |
| R3 | Cria `downloads/<YYYY-MM-DD>-<slug-do-titulo>/` e grava o vídeo lá dentro | Conferir o caminho e o slug de um título com acentos e pontuação |
| R4 | Grava `metadata.json` com url, plataforma, id, título, autor, duração, data de publicação, data do download e versão do yt-dlp usada | Ler o JSON e conferir os campos |
| R5 | Usa o yt-dlp do projeto, nunca o do sistema, e falha com `ENVIRONMENT` se a versão for anterior à mínima | Forçar um yt-dlp antigo no PATH e conferir que recusa (ver L-009) |
| R6 | Passa um runtime JavaScript ao yt-dlp, localizando o `node` sem supor que está no PATH | Rodar num shell sem nvm carregado (ver L-003) |
| R7 | Falhas conhecidas viram mensagem acionável com `hint`: vídeo privado, removido, bloqueado por região, 403 por yt-dlp velho, rate limit | Testar com um vídeo privado e um id inexistente |
| R8 | Não baixa de novo o que já está em disco: se a pasta já tem o vídeo, retorna o caminho existente | Rodar duas vezes seguidas e comparar o tempo e o mtime |
| R9 | Obedece ao contrato de I/O: um JSON em stdout, log em stderr, exit code correto | Coberto pelos testes do contrato e por um teste do script |

## Fora de escopo

- Instagram (é o M2/F6)
- Conteúdo que exija autenticação
- Playlists e múltiplas URLs
- Escolha de resolução pelo usuário

## Decisões herdadas

- `--download-sections` não é usado: o YouTube responde 403 (L-004)
- A versão do yt-dlp entra no `metadata.json` porque a transcrição não é reproduzível e a origem precisa ser rastreável (L-008)
