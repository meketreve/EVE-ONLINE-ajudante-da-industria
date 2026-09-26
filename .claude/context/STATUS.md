# Status — atualizado em 2026-09-26

## Estado atual
App NiceGUI funcional (calculadora, fila, ranking de importação, reprocessamento, mercados de estruturas).
Primeiro uso sem configuração pronto e em `main`: login PKCE com Client ID embutido, SDE e preços de Jita
automáticos, checklist no Dashboard, lista de personagens em Configurações, `Iniciar.bat` e `iniciar.sh`.

## Próxima fase
- Publicar a primeira release (v1.0.0) com o skill `/release`: sem ela o autoupdate não tem o que baixar.
- Testar o `Iniciar.bat` num Windows real, de preferência sem Python instalado (só foi revisado, não executado).

## Pendências e bloqueios
- Sem testes automatizados nem config de lint no repo.

## Concluído (recente)
- 2026-09-26: autoupdate por GitHub Release (`atualizar.py` + launchers), WORKFLOW de release e skill `/release`.
- 2026-09-24: onboarding de primeiro uso, correção do import do SDE (EVERef/Fuzzwork), launchers, README.
