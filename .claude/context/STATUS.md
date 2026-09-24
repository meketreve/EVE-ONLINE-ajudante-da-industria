# Status — atualizado em 2026-09-24

## Estado atual
App NiceGUI funcional (calculadora, fila, ranking de importação, reprocessamento, mercados de estruturas).
Primeiro uso sem configuração pronto e em `main`: login PKCE com Client ID embutido, SDE e preços de Jita
automáticos, checklist no Dashboard, lista de personagens em Configurações, `Iniciar.bat` e `iniciar.sh`.

## Próxima fase
- Testar o `Iniciar.bat` num Windows real, de preferência sem Python instalado (só foi revisado, não executado).
- Decidir o que fazer com os ~30 arquivos que diferem só em fim de linha (CRLF) no working tree.

## Pendências e bloqueios
- `CLAUDE.md` da raiz ainda descreve a stack antiga (FastAPI/Jinja/HTMX); a atual é NiceGUI.
- Sem testes automatizados nem config de lint no repo.

## Concluído (recente)
- 2026-09-24: onboarding de primeiro uso, correção do import do SDE (EVERef/Fuzzwork), launchers, README.
