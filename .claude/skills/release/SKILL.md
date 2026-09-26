---
name: release
description: Monta e publica uma GitHub Release do EVE Industry Tool (atualiza VERSION, notas em português, gh release create) para o autoupdate entregar aos usuários. Usar quando o usuário pedir release, lançar versão, publicar atualização, ou aceitar a sugestão de release do WORKFLOW.
---

# Montar release

Os launchers rodam `atualizar.py`, que instala a última release se o `VERSION` dela for maior que o local.
O zip da release **precisa** ter `VERSION` igual à tag (sem o `v`), senão o updater recusa a instalação.

## 1. Conferir o estado
```bash
git switch main && git fetch -q && git status -sb        # limpo e sincronizado com origin/main
git describe --tags --abbrev=0 2>/dev/null || echo "sem tag ainda"
git log $(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)..HEAD --oneline
```
Parar e avisar se: há mudanças não commitadas, a `main` está atrás/à frente do GitHub, ou não há commits novos.

## 2. Checagens antes de publicar
- Diff desde a última tag sem dados sensíveis: `git diff <última-tag>..HEAD | grep -nE "eat_|refresh_token.*=|EVE_CLIENT_SECRET=\S"`,
  e nenhum `database.db*`, `.env`, `.secret_key`, `.nicegui/` em `git diff --name-only <última-tag>..HEAD`.
- `python3 -m py_compile` em todos os `.py` versionados.
- `Iniciar.bat`: `file Iniciar.bat` → ASCII + CRLF; `grep -n '[<>]' Iniciar.bat | grep -v '>nul'` vazio.
- `iniciar.sh`: shellcheck, se disponível.
- Confirmar com o usuário que as features da lista foram **testadas**.

## 3. Escolher a versão
Pelas mensagens de commit desde a última tag (ver semver em `.claude/context/WORKFLOW.md`): `fix` → patch,
`feat` → minor, quebra de compatibilidade → major. **Propor a versão e confirmar com o usuário.**

## 4. Notas da release (em português, para usuário leigo)
Escrever em `$SCRATCHPAD/notas-vX.Y.Z.md`, a partir dos commits, sem jargão:
```markdown
## Novidades
- ...
## Correções
- ...
## Como atualizar
Feche e abra o programa pelo `Iniciar.bat` (Windows) ou `iniciar.sh` (Linux): a atualização é automática.
Primeira instalação: baixe o **Source code (zip)** abaixo, extraia e rode o `Iniciar.bat`.
```

## 5. Publicar (pedir confirmação antes: é público)
```bash
echo "X.Y.Z" > VERSION
git add VERSION && git commit -m "release: vX.Y.Z" && git push origin main
gh release create vX.Y.Z --target main --title "vX.Y.Z" --notes-file "$SCRATCHPAD/notas-vX.Y.Z.md"
```

## 6. Verificar
- `gh release view vX.Y.Z` mostra a release.
- O zip tem `VERSION` certo e não tem `.claude/` nem `CLAUDE.md` (export-ignore):
  `curl -sL <zipball_url> -o r.zip && unzip -l r.zip | grep -E "VERSION|\.claude|CLAUDE"`
- Numa cópia em scratch **sem `.git`** e com `VERSION` antigo, `python3 atualizar.py` detecta e instala a versão nova.

## 7. Registrar
Atualizar `.claude/context/STATUS.md` ("Concluído": vX.Y.Z publicada) e responder ao usuário com o link da release.
