"""
BOM tree component — recursive render.

Features:
- Expand/collapse por nó fabricado (2 primeiros níveis abertos por padrão)
- Borda colorida por profundidade
- Subtotal de custo por componente fabricado
- Coluna de Runs nos nós fabricados
- Campo ME editável por sub-componente (com debounce)
- Chip de toggle Fabricar/Comprar com ícone
- Rodapé com total consolidado
"""

import asyncio
import json
import logging

from nicegui import ui

from app.services.blueprint_service import BOMNode

logger = logging.getLogger(__name__)

# Cor da borda esquerda por profundidade
_DEPTH_COLORS = ["#5c8ee8", "#4ab8c1", "#4aab6e", "#c4a83a", "#888888"]


def _depth_color(depth: int) -> str:
    return _DEPTH_COLORS[min(depth, len(_DEPTH_COLORS) - 1)]


def _fmt(value: float) -> str:
    if value == 0:
        return "—"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f} M"
    return f"{value:,.0f}"


def _flatten_bom(node: BOMNode, depth: int = 0) -> list[dict]:
    """Retorna lista plana de todos os nós do BOM com seus dados."""
    node_type = "Fabricar" if (node.is_manufactured and not node.buy_as_is) else "Comprar"
    rows = [{
        "name":       node.type_name,
        "quantity":   node.quantity,
        "node_type":  node_type,
        "unit_price": node.unit_price or 0.0,
        "total_cost": node.total_cost or 0.0,
    }]
    for child in node.children:
        rows.extend(_flatten_bom(child, depth + 1))
    return rows


def _count_distinct_leaves(node: BOMNode, seen: set | None = None) -> int:
    if seen is None:
        seen = set()
    if node.is_leaf or node.buy_as_is:
        seen.add(node.type_id)
    for child in node.children:
        _count_distinct_leaves(child, seen)
    return len(seen)


# ── Componente público ────────────────────────────────────────────────────────

def render_bom_tree(
    root: BOMNode,
    on_toggle=None,
    on_me_change=None,
    on_station_change=None,
    available_stations=None,
):
    """
    Renderiza a árvore BOM com expand/colapso, subtotais e ME por componente.

    Parameters
    ----------
    root               : raiz da árvore BOMNode (já enriquecida com custos)
    on_toggle          : async callable(type_id) — alterna Fabricar/Comprar
    on_me_change       : async callable(type_id, new_me) — atualiza ME do componente
    on_station_change  : async callable(type_id, station_id | None) — altera estação do nó
    available_stations : lista de ManufacturingStructure disponíveis para o select
    """
    distinct = _count_distinct_leaves(root)

    # Monta opções de estação uma vez para toda a árvore
    station_opts: dict = {0: "Global"}
    for s in (available_stations or []):
        station_opts[s.id] = f"{s.name} (ME {s.me_bonus:.1f}%)"

    # Prepara textos de cópia a partir da árvore
    _flat = _flatten_bom(root)
    _list_text = "\n".join(f"{r['name']} {r['quantity']:,}" for r in _flat)
    _csv_rows  = ["Material,Quantidade,Tipo,Preco Unitario (ISK),Total (ISK)"]
    for _r in _flat:
        _n = _r["name"].replace('"', '""')
        _csv_rows.append(
            f'"{_n}",{_r["quantity"]},{_r["node_type"]},{_r["unit_price"]:.2f},{_r["total_cost"]:.2f}'
        )
    _csv_text = "\n".join(_csv_rows)

    with ui.card().classes("q-pa-md bg-grey-9 w-full"):

        # ── Cabeçalho ─────────────────────────────────────────────────────────
        with ui.row().classes("items-center gap-2 q-mb-xs"):
            ui.icon("account_tree").classes("text-blue-grey-4 text-lg")
            ui.label("Árvore BOM Recursiva").classes("text-subtitle1 text-white font-bold")
            hints = []
            if on_toggle or on_me_change:
                hints.append("Chip = Fabricar/Comprar  ·  ME editável")
            if on_station_change:
                hints.append("Estação por sub-componente")
            if hints:
                ui.label("  ·  ".join(hints)).classes("text-caption text-grey-6 q-ml-sm")

            async def _copy_bom_list(t=_list_text):
                await ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(t)})")
                ui.notify("Lista BOM copiada!", type="positive", position="top-right", timeout=2000)

            async def _copy_bom_csv(t=_csv_text):
                await ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(t)})")
                ui.notify("CSV BOM copiado!", type="positive", position="top-right", timeout=2000)

            with ui.row().classes("q-ml-auto gap-1"):
                ui.button("Lista", icon="content_copy", on_click=_copy_bom_list).props(
                    "flat dense color=grey-5 size=sm"
                ).tooltip("Copia todos os componentes como lista (nome + quantidade)")
                ui.button("CSV", icon="table_view", on_click=_copy_bom_csv).props(
                    "flat dense color=teal-5 size=sm"
                ).tooltip("Copia todos os componentes em formato CSV para Excel / Google Sheets")

        # ── Cabeçalho das colunas ─────────────────────────────────────────────
        with ui.row().classes(
            "w-full items-center text-grey-5 text-xs q-pb-xs q-px-sm"
        ).style("gap:4px"):
            ui.element("div").style("width:24px;flex-shrink:0")          # expand btn
            ui.label("Material").classes("flex-1 min-w-0")
            ui.label("Qtd").classes("text-right").style("width:72px;flex-shrink:0")
            ui.label("Runs").classes("text-right").style("width:52px;flex-shrink:0")
            ui.label("ME").classes("text-center").style("width:76px;flex-shrink:0")
            if on_station_change:
                ui.label("Estação").classes("text-center").style("width:160px;flex-shrink:0")
            ui.label("Preço/un").classes("text-right").style("width:96px;flex-shrink:0")
            ui.label("Total (ISK)").classes("text-right").style("width:108px;flex-shrink:0")
            ui.label("Tipo").classes("text-center").style("width:112px;flex-shrink:0")

        ui.separator().classes("q-mb-xs")

        # ── Árvore ────────────────────────────────────────────────────────────
        with ui.column().classes("w-full").style("gap:0"):
            _render_node(
                root, depth=0,
                on_toggle=on_toggle, on_me_change=on_me_change,
                on_station_change=on_station_change, station_opts=station_opts,
            )

        # ── Rodapé ────────────────────────────────────────────────────────────
        ui.separator().classes("q-mt-xs q-mb-xs")
        with ui.row().classes("items-center justify-between q-px-sm text-caption"):
            ui.label(f"{distinct} materiais distintos a comprar").classes("text-grey-5")
            color = "text-green-4" if root.total_cost > 0 else "text-grey-5"
            ui.label(
                f"Custo total estimado: {_fmt(root.total_cost)} ISK"
            ).classes(f"{color} font-bold")


# ── Renderização recursiva ────────────────────────────────────────────────────

def _render_node(node: BOMNode, depth: int, on_toggle, on_me_change, on_station_change=None, station_opts: dict | None = None):
    """Renderiza um nó e seus filhos recursivamente com expand/colapso."""

    can_expand = bool(node.children)
    is_expanded = [depth < 2]          # mutable para closure
    border_col  = _depth_color(depth)

    # Estilo do nome por tipo/profundidade
    if depth == 0:
        name_cls = "text-white text-body2 font-bold"
    elif node.is_leaf or node.buy_as_is:
        name_cls = "text-grey-3 text-caption"
    else:
        name_cls = "text-cyan-3 text-caption font-medium"

    # Rótulo e cor do chip de tipo
    if node.buy_as_is:
        chip_label = "Comprar (manual)"
        chip_color = "warning"
        chip_icon  = "shopping_cart"
    elif node.is_manufactured and not node.is_leaf:
        chip_label = "Fabricar"
        chip_color = "blue-7"
        chip_icon  = "build"
    else:
        chip_label = "Comprar"
        chip_color = "grey-7"
        chip_icon  = "shopping_cart"

    can_toggle = (
        on_toggle is not None
        and depth > 0
        and (node.is_manufactured or node.buy_as_is)
    )

    # ── Linha do nó ──────────────────────────────────────────────────────────
    with ui.row().classes(
        "w-full items-center rounded hover:bg-grey-8"
    ).style(
        f"padding: 3px {8}px 3px {depth * 16 + 4}px;"
        f"border-left: 2px solid {border_col};"
        f"gap: 4px;"
    ):
        # Botão expand/colapso
        if can_expand:
            expand_btn = ui.button(
                icon="expand_more" if is_expanded[0] else "chevron_right"
            ).props("flat round dense size=xs color=grey-5").style("width:24px;flex-shrink:0")
        else:
            ui.element("div").style("width:24px;flex-shrink:0")

        # Nome do item
        ui.label(node.type_name).classes(f"flex-1 min-w-0 {name_cls}").style(
            "white-space:nowrap;overflow:hidden;text-overflow:ellipsis"
        )

        # Quantidade
        ui.label(f"{node.quantity:,}").classes(
            "text-right text-grey-3 text-caption"
        ).style("width:72px;flex-shrink:0")

        # Runs (fabricados com blueprint)
        if node.is_manufactured and node.blueprint_runs and not node.buy_as_is:
            ui.label(f"{node.blueprint_runs}×").classes(
                "text-right text-blue-grey-4 text-caption"
            ).style("width:52px;flex-shrink:0")
        else:
            ui.element("div").style("width:52px;flex-shrink:0")

        # ME override — disponível para todos os nós fabricados (incluindo root)
        if on_me_change and node.is_manufactured and not node.buy_as_is:
            _me_timer = [None]
            tid_cap   = node.type_id

            async def _on_me_input(e, tid=tid_cap):
                if e.value is None:
                    return
                new_me = max(0, min(10, int(e.value or 0)))
                if _me_timer[0]:
                    _me_timer[0].cancel()
                async def _fire(m=new_me, t=tid):
                    await on_me_change(t, m)
                _me_timer[0] = ui.timer(0.5, _fire, once=True)

            me_num = ui.number(
                value=node.me_level, min=0, max=10, step=1,
            ).style("width:76px;flex-shrink:0").props(
                "outlined dense dark hide-bottom-space no-error-icon"
            )
            me_num.on_value_change(_on_me_input)
        else:
            ui.element("div").style("width:76px;flex-shrink:0")

        # Seletor de estação (todos os nós fabricados, incluindo root)
        if on_station_change and node.is_manufactured and not node.buy_as_is:
            tid_cap_s = node.type_id
            current_station = node.station_id or 0

            async def _on_station_change(e, tid=tid_cap_s):
                val = e.value
                sid = None if (val is None or val == 0) else int(val)
                await on_station_change(tid, sid)

            station_sel = ui.select(
                options=station_opts or {0: "Global"},
                value=current_station,
            ).style("width:160px;flex-shrink:0").props(
                "outlined dense dark hide-bottom-space"
            )
            station_sel.on_value_change(_on_station_change)
        elif on_station_change:
            # coluna presente mas nó não elegível — espaço reservado
            ui.element("div").style("width:160px;flex-shrink:0")

        # Preço unitário
        if node.unit_price:
            p_cls = "text-green-4" if (node.is_leaf or node.buy_as_is) else "text-cyan-3"
            ui.label(_fmt(node.unit_price)).classes(
                f"text-right text-caption {p_cls}"
            ).style("width:96px;flex-shrink:0")
        else:
            ui.label("—").classes("text-right text-grey-6 text-caption").style(
                "width:96px;flex-shrink:0"
            )

        # Custo total do nó
        if node.total_cost:
            t_cls = "text-green-4" if (node.is_leaf or node.buy_as_is) else "text-yellow-5"
            ui.label(f"{_fmt(node.total_cost)} ISK").classes(
                f"text-right text-caption font-medium {t_cls}"
            ).style("width:108px;flex-shrink:0")
        else:
            ui.label("—").classes("text-right text-grey-6 text-caption").style(
                "width:108px;flex-shrink:0"
            )

        # Chip de tipo / toggle
        if can_toggle:
            tid_cap2     = node.type_id
            toggle_hint  = "→ Comprar" if not node.buy_as_is else "→ Fabricar"
            chip_btn = ui.button(chip_label, icon=chip_icon).props(
                f"unelevated dense size=sm color={chip_color} no-caps"
            ).style("width:112px;flex-shrink:0").tooltip(toggle_hint)
            chip_btn.on_click(
                lambda tid=tid_cap2: asyncio.ensure_future(on_toggle(tid))
            )
        else:
            ui.badge(chip_label, color=chip_color).classes("text-caption").style(
                "width:112px;flex-shrink:0;text-align:center"
            )

    # ── Filhos (expansível) ───────────────────────────────────────────────────
    if can_expand:
        children_col = ui.column().classes("w-full").style("gap:0")
        children_col.set_visibility(is_expanded[0])

        # Lazy render: só renderiza filhos se o nó começa expandido.
        # Nós colapsados (depth >= 2) renderizam os filhos na primeira expansão.
        rendered = [is_expanded[0]]
        if is_expanded[0]:
            with children_col:
                for child in node.children:
                    _render_node(child, depth + 1, on_toggle, on_me_change, on_station_change, station_opts)

        async def _toggle_expand():
            is_expanded[0] = not is_expanded[0]
            if is_expanded[0] and not rendered[0]:
                rendered[0] = True
                with children_col:
                    for child in node.children:
                        _render_node(child, depth + 1, on_toggle, on_me_change, on_station_change, station_opts)
            children_col.set_visibility(is_expanded[0])
            expand_btn._props["icon"] = (
                "expand_more" if is_expanded[0] else "chevron_right"
            )
            expand_btn.update()

        expand_btn.on_click(_toggle_expand)
