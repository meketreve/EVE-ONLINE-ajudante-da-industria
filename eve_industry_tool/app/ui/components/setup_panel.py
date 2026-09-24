"""
UI da preparação do primeiro uso.

first_run_banner()  — aviso no topo das páginas enquanto dados do jogo/preços
                      são baixados em background, ou se algo falhou.
setup_checklist()   — checklist no Dashboard com o que está pronto e o que falta.
"""

import asyncio

from nicegui import ui

from app.services import first_run
from app.services.first_run import tasks

_TASK_TITLES = {
    "sde":    "Dados do jogo",
    "prices": "Preços de Jita",
}


def _start(task: str) -> None:
    job = first_run.ensure_sde(force=True) if task == "sde" else first_run.ensure_hub_prices(force=True)
    asyncio.create_task(job, name=f"first_run_{task}")
    ui.notify(f"{_TASK_TITLES[task]}: iniciado em segundo plano.", type="info")


def first_run_banner() -> None:
    card = ui.card().classes("w-full q-pa-md bg-blue-grey-9 q-mb-md")
    rows = {}
    with card:
        ui.label("Preparando o EVE Industry Tool").classes("text-white font-bold")
        for key, title in _TASK_TITLES.items():
            with ui.row().classes("items-center gap-3 w-full no-wrap") as row:
                spinner = ui.spinner("dots", size="sm", color="blue-grey-3")
                icon = ui.icon("error").classes("text-orange-5 text-xl")
                with ui.column().classes("gap-0 flex-1"):
                    ui.label(title).classes("text-caption text-grey-3 font-bold")
                    msg = ui.label().classes("text-caption text-grey-5")
                    bar = ui.linear_progress(show_value=False).props("color=blue-grey-4")
                retry = ui.button("Tentar de novo", icon="refresh",
                                  on_click=lambda k=key: _start(k)).props("flat dense color=orange-4")
            rows[key] = (row, spinner, icon, msg, bar, retry)
        ui.label(
            "Acontece só no primeiro uso. Você pode continuar usando o app enquanto isso."
        ).classes("text-caption text-grey-6 q-mt-xs")

    def refresh():
        visible = False
        for key, (row, spinner, icon, msg, bar, retry) in rows.items():
            t = tasks[key]
            show = t["state"] in ("running", "error")
            visible |= show
            row.set_visibility(show)
            spinner.set_visibility(t["state"] == "running")
            icon.set_visibility(t["state"] == "error")
            retry.set_visibility(t["state"] == "error")
            msg.set_text(t["message"])
            bar.set_visibility(t["state"] == "running")
            if t["progress"] is None:
                bar.props("indeterminate")
            else:
                bar.props(remove="indeterminate")
                bar.set_value(t["progress"])
        card.set_visibility(visible)

    refresh()
    ui.timer(1.0, refresh)


async def setup_checklist(character_id: int | None) -> None:
    """
    Card de checklist; recolhe sozinho quando o essencial está pronto.

    Só reconstrói o card quando algum passo muda de estado (feito/rodando);
    o texto de progresso das tarefas é atualizado no lugar, sem piscar.
    """
    # open: None = automático (aberto enquanto faltar algo); True/False = escolha do usuário
    state: dict = {"sig": None, "open": None}
    live_labels: dict[str, ui.label] = {}

    def _signature(items: list[dict]) -> tuple:
        return tuple(
            (i["key"], i["done"], bool(i.get("warning")),
             i["action"] in tasks and first_run.is_running(i["action"]))
            for i in items
        )

    @ui.refreshable
    async def render(items: list[dict]):
        live_labels.clear()
        required = [i for i in items if not i["optional"]]
        n_done = sum(i["done"] for i in required)
        all_done = n_done == len(required)
        n_warn = sum(bool(i.get("warning")) for i in items)
        is_open = state["open"] if state["open"] is not None else not all_done or bool(n_warn)

        if not all_done:
            title, icon = f"Primeiros passos — {n_done} de {len(required)} concluídos", "checklist"
        elif n_warn:
            title, icon = f"Pronto para usar — {n_warn} aviso(s)", "error_outline"
        else:
            title, icon = "Tudo pronto para usar", "task_alt"
        exp = ui.expansion(title, icon=icon, value=is_open) \
            .classes("w-full bg-grey-9 text-white q-mb-lg rounded")
        exp.on_value_change(lambda e: state.update(open=e.value))
        with exp:
            ui.linear_progress(value=n_done / len(required), show_value=False) \
                .props(f"color={'positive' if all_done else 'blue-grey-4'}").classes("q-mb-sm")
            for item in items:
                _checklist_row(item)

    def _checklist_row(item: dict):
        running = item["action"] in tasks and first_run.is_running(item["action"])
        with ui.row().classes("items-center gap-3 w-full no-wrap q-py-xs q-px-sm"):
            if running:
                ui.spinner("dots", size="sm", color="blue-grey-3")
            elif item["done"] and item.get("warning"):
                ui.icon("error_outline").classes("text-orange-4 text-xl")
            elif item["done"]:
                ui.icon("check_circle").classes("text-green-5 text-xl")
            else:
                ui.icon("radio_button_unchecked").classes(
                    "text-grey-6 text-xl" if item["optional"] else "text-orange-4 text-xl"
                )
            with ui.column().classes("gap-0 flex-1"):
                with ui.row().classes("items-center gap-2"):
                    ui.label(item["title"]).classes("text-white text-body2")
                    if item["optional"]:
                        ui.badge("opcional", color="grey-8").props("outline")
                detail = tasks[item["action"]]["message"] if running else item["detail"]
                label = ui.label(detail).classes("text-caption text-grey-5")
                if running:
                    live_labels[item["action"]] = label

            action = item["action"]
            if running:
                return
            if action in tasks:
                text = "Atualizar" if item["done"] else "Baixar agora"
                ui.button(text, icon="download", on_click=lambda a=action: _start(a)) \
                    .props("flat dense color=blue-grey-3")
            elif (not item["done"] or item.get("warning")) and action:
                ui.button("Abrir", icon="arrow_forward", on_click=lambda p=action: ui.navigate.to(p)) \
                    .props("flat dense color=blue-grey-3")

    items = await first_run.get_checklist(character_id)
    state["sig"] = _signature(items)
    await render(items)

    async def poll():
        # Texto de progresso: atualiza no lugar
        for task, label in live_labels.items():
            label.set_text(tasks[task]["message"])
        # Estrutura: só reconstrói quando algum passo muda de estado
        if not first_run.is_running() and not live_labels:
            return
        items = await first_run.get_checklist(character_id)
        sig = _signature(items)
        if sig != state["sig"]:
            state["sig"] = sig
            await render.refresh(items)

    ui.timer(2.0, poll)
