---
updated: 2026-10-02
tier: 2
---

# Aprendizados

<!-- TETO: 100 linhas. Uma linha por fato, formato grepável: `- [AAAA-MM-DD] [tag] fato — consequência`. -->

## Preferências do usuário
- [2026-09-24] [prefs] Foco em facilitar o primeiro uso por usuário leigo (Windows). Textos de UI em português.
- [2026-09-24] [prefs] NUNCA commitar dados de personagens nem sensíveis: `database.db*`, `.env`, `.secret_key`, `.nicegui/`, Client Secret, nomes/IDs de personagens em docs. Conferir o diff antes de commitar.
- [2026-09-24] [prefs] Pode fazer push direto na `main` quando pedir.

## Pegadinhas (versão, API, CI)
- [2026-09-24] [sde] EVERef: reprocessamento está em `types.json[tid].type_materials`; `type_materials.json` vem vazio.
- [2026-09-24] [sde] Fuzzwork SQLite mudou para `https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz` (gzip); tabelas iguais.
- [2026-09-24] [bat] `.bat`: `<`/`>` fora de aspas viram redirecionamento; aspas aninhadas em `set "X=..."` deixam trechos de fora.
- [2026-09-24] [python] Janela nativa no Windows depende de pythonnet: usar Python 3.11–3.13.
- [2026-09-24] [nicegui] NiceGUI: passar `window_size` força `native`; `refreshable.refresh()` em timer recria o elemento (pisca).
- [2026-09-24] [sso] Refresh token sem uso há meses volta `invalid_grant`: personagem precisa logar de novo.
- [2026-09-24] [sso] Personagem "conectado" = `refresh_token IS NOT NULL` (discovery e crawler já filtram assim).
- [2026-09-24] [nicegui] Log do NiceGUI pode ter bytes binários: usar `grep -a`.
- [2026-09-24] [git] Push direto na main com checkout bloqueado por arquivos locais: `git push origin <branch>:main` (fast-forward) e `git branch -f main`.
- [2026-09-24] [db] Migrations ficam em `database.py → create_tables()` como blocos `ALTER TABLE` (sem Alembic). TTLs: mercado de região 5 min, estrutura 4 h, skills 1 h, info de estrutura 24 h.
- [2026-09-24] [github] Repo mudou para `meketreve/EVE-ONLINE-ajudante-da-industria` (sem traço triplo).

- [2026-09-26] [autoupdate] `zipfile` do Python não restaura permissões: o updater reaplica o bit de execução a partir de `external_attr`; o `.sh` relança com `exec bash`.
- [2026-09-26] [launcher] cmd e bash leem o script enquanto executam: atualizar + reiniciar o launcher tem que ficar no mesmo bloco `( )` / `if ... fi`.
- [2026-09-26] [git] `.claude/settings.local.json` estava versionado desde o 1º commit (antes do `.gitignore`); removido do índice.

- [2026-10-02] [sessao] Sessão fica em `.nicegui/storage-general.json` (`character_id`/`character_name`); o startup restaura em vez de limpar. Logout apaga as chaves e é respeitado na próxima abertura. O access token não vai mais para esse arquivo.

- [2026-10-02] [autoupdate] O update roda o `atualizar.py` **já instalado**: mudança no próprio updater só vale a partir da release seguinte — testar sempre a partir do zip da release anterior.
- [2026-10-02] [autoupdate] Aviso de novidades: `.novidades.json` do updater ou, se faltar, o app busca `releases/tags/v{VERSION}` no startup (`novidades.prepare_news`); `last_seen_version` na sessão evita repetir.
- [2026-10-02] [teste] Servidor de teste em background: matar pelo PID que escuta a porta (`ss -ltnp`) e esperar liberar; `$!` de `(cd ... && cmd &)` é do subshell, não do Python.
- [2026-10-02] [ci] `EVE_TOOL_SMOKE=1`: `app.main` importa tudo, checa pywebview/pythonnet, roda `init_db` e sai 0; o `.bat` troca `pause` por `rem` e devolve o código do app. Release falsa do CI usa URLs `file://` (`.github/scripts/fake_release.py`).
- [2026-10-02] [ci] No CI Windows, gravar/conferir arquivo com `Set-Content`/`Get-Content -Raw` do PowerShell deu falso negativo; usar `python -c` para gravar e comparar (igual nos dois SOs).

## Erros a não repetir
- [2026-09-24] [shell] `pkill -f <padrão>` que casa com o próprio comando mata o shell da ferramenta. Matar pelo PID (via `ss -ltnp`).
- [2026-09-24] [bat] Arquivos da raiz com CRLF (`.bat`): preservar; `.gitignore` e código em LF (HEAD é LF).

## Decisões e o porquê
- [2026-09-26] [decisão] Autoupdate por **GitHub Release** (não por commit): o usuário só recebe o que foi marcado como pronto. Updater valida o zip (arquivos obrigatórios + VERSION = tag) e não apaga mais de 30% dos arquivos.
- [2026-09-24] [decisão] Login PKCE com Client ID embutido: usuário não cria app nem `.env`. Secret opcional só no `.env` local.
- [2026-09-24] [decisão] Primeiro uso automático + checklist em vez de passos manuais no README.
- [2026-09-24] [decisão] OpenWolf removido (`.wolf/`, hooks e regras); o contexto do projeto fica só em `.claude/context/`.
- [2026-09-24] [decisão] `.gitattributes`: `*.bat -text` (mantém CRLF no ZIP do GitHub), `*.sh eol=lf`.
