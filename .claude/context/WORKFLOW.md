# Workflow do projeto

<!-- Adotado em 2026-09-26. Vale para: toda feature ou correção que chega ao usuário final. -->

Os usuários recebem código novo **só por GitHub Release**: o `atualizar.py` (chamado pelos launchers) baixa a
última release e compara com o arquivo `VERSION`. Commit na `main` sem release não chega a ninguém.

1. **Desenvolver** — na `main` (ou branch, se o usuário pedir). *Pronto quando:* o código compila e faz o que foi pedido.
2. **Testar** — rodar o app de verdade (`./iniciar.sh`, ou cópia em scratch sem `.git` para simular usuário novo)
   e exercitar a feature. *Pronto quando:* o fluxo foi visto funcionando, não só compilado.
3. **Commit + push** — só quando o usuário pedir. *Pronto quando:* `main` sincronizada com o GitHub.
4. **Lembrar da release** — ao concluir e testar uma feature ou correção que o usuário final vai notar,
   **perguntar**: "Quer montar a release vX.Y.Z com isso?" (sugerir a versão). Também lembrar no fim da sessão se
   houver commits `feat`/`fix` desde a última tag (`git log $(git describe --tags --abbrev=0)..HEAD --oneline`).
   Não criar release sem um "sim".
5. **Release** — seguir o skill `/release`. *Pronto quando:* a release aparece em `gh release view` e o
   `atualizar.py` numa cópia sem `.git` detecta a versão nova.

## Versão (semver)
- **patch** (1.2.3 → 1.2.4): só correções.
- **minor** (1.2.3 → 1.3.0): feature nova, sem quebrar nada.
- **major** (1.2.3 → 2.0.0): muda algo que o usuário precisa refazer (banco incompatível, configuração perdida).

## Antes de commitar
- [ ] Diff sem dados sensíveis (tokens, Client Secret, nomes/IDs de personagens, `database.db*`, `.env`, `.secret_key`)
- [ ] `python -m py_compile` nos arquivos Python alterados
- [ ] `Iniciar.bat` continua ASCII + CRLF e sem `<`/`>` fora de aspas; `iniciar.sh` passa no shellcheck
- [ ] README atualizado se a mudança aparece para o usuário
