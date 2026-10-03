---
updated: 2026-10-02
tier: 2
---

# Status — tier 2+

<!-- TETO: 60 linhas. Resumir "Concluído" quando crescer. -->

## Estado atual

App NiceGUI funcional (calculadora, fila, ranking de importação, reprocessamento, mercados de estruturas).
**v1.1.1 publicada** (Latest): primeiro uso sem configuração, login PKCE mantido entre aberturas, autoupdate
por GitHub Release com aviso "O que há de novo" e versão no rodapé. Usuários recebem só o que vira release.

## Próxima fase

- Testar o `Iniciar.bat` num Windows real (instalação + reinício após autoupdate); nunca foi executado.

## Pendências e bloqueios

- Sem testes automatizados nem config de lint no repo.

## Concluído (recente)

- v1.1.1 (2026-10-02): aviso de novidades também para quem veio da v1.0.0 (app busca as notas no GitHub).
- v1.1.0 (2026-10-02): login mantido, aviso de novidades, versão no rodapé · v1.0.0 (2026-09-26): primeiro
  uso sem configuração, autoupdate, workflow `/release`.

## Bruto do git (auto — não editar)

<!-- auto:start -->
data: 2026-10-02

```
e796172 docs(context): formato tier 2 do /contexto e registro da v1.1.0
7f177a9 release: v1.1.0
5dcc880 feat: login mantido entre aberturas e aviso "O que há de novo"
3f87f3e docs(context): registra a release v1.0.0
6cdca4c feat: atualização automática por GitHub Release
a91141b docs: CLAUDE.md reescrito para a stack NiceGUI atual
2356ed0 docs: README com notas de desenvolvimento e fim de linha
6c44c6c chore: substitui OpenWolf por .claude/context
a0e6923 docs: atualiza README (Linux, primeiro uso, personagens, problemas comuns)
ed536e3 chore(first_run): loga quando os preços de Jita terminam de carregar
e77fe05 fix(Iniciar.bat): detecção de Python e fim de linha dos scripts
5f1433f feat: primeiro uso sem configuração para usuário leigo
0e3339d Readme.md update and file cleanup
de4506a Update README.md
ca75d33 refactor: migra stack para NiceGUI, melhora cache-first e background jobs
--- status ---
```
<!-- auto:end -->
