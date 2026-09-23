# F5 — Skill orquestradora

**Natureza:** não determinística. Encadear é trivial; o que exige julgamento é decidir o que fazer quando uma etapa falha no meio, e o que vale contar ao usuário no fim.

## O que a idempotência já resolve

Download, extração e transcrição devolvem `reused: true` quando o trabalho já está feito. Retomar uma execução interrompida é, portanto, simplesmente rodar tudo de novo: as etapas prontas respondem em segundos e só o que falta é executado. Não há máquina de estados a construir, e é por isso que esta feature é pequena.

## Requisitos

| ID | Requisito | Verificação |
|---|---|---|
| R1 | A partir de uma URL, executa download → extração → transcrição e devolve tudo o que foi produzido | Rodar com um link novo |
| R2 | Uma execução interrompida é retomada sem refazer o que já estava pronto | Interromper no meio e rodar de novo |
| R3 | Falha em qualquer etapa interrompe o encadeamento e identifica em qual delas foi | Forçar falha no download |
| R4 | O exit code e a dica da etapa que falhou são preservados, não traduzidos | Conferir o código propagado |
| R5 | O resultado final reúne caminho da pasta, título, duração, idioma, modelo e os três arquivos de transcrição | Ler o JSON |
| R6 | Obedece ao contrato de I/O | Teste de linha de comando |

## Fora de escopo

- Várias URLs por execução
- Paralelismo entre etapas — elas são sequencialmente dependentes
- Repetir automaticamente uma etapa que falhou: se o YouTube limitou a taxa, insistir piora
