import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, callback
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np
from data import loader

dash.register_page(__name__, path="/evolution", name="Evolution", order=1)

# Colour palette to visually distinguish scenarios (applied as bar opacity / outline)
SCENARIO_PATTERNS = {}   # can be extended later

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dbc.Container([
    # ── Filter strip row 1 ────────────────────────────────────────────────
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("View", className="form-label-sm"),
            dcc.RadioItems(
                id="evo-view",
                options=[
                    {"label": " Absolute",   "value": "Absolute"},
                    {"label": " Difference", "value": "Difference"},
                    {"label": " % Share",    "value": "Percentage"},
                ],
                value="Absolute", inline=True, className="mt-1",
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "12px", "fontSize": "0.85rem"},
            ),
        ], md=3),
        dbc.Col([
            html.Label("Indicator", className="form-label-sm"),
            dcc.Dropdown(
                id="evo-indicator",
                options=loader.INDICATOR_OPTIONS,
                value="CapacityTechFuel",
                clearable=False,
                style={"fontSize": "0.85rem"},
            ),
        ], md=3),
        dbc.Col([
            html.Label("Scenarios", className="form-label-sm"),
            dcc.Dropdown(id="evo-scenarios", multi=True,
                         placeholder="All scenarios",
                         style={"fontSize": "0.85rem"}),
        ], md=3),
        dbc.Col([
            html.Label("Reference Scenario", className="form-label-sm"),
            dcc.Dropdown(id="evo-ref-scenario", clearable=False,
                         style={"fontSize": "0.85rem"}),
        ], md=3),
    ], className="g-2")), className="mb-2 shadow-sm filter-card"),

    # ── Filter strip row 2 ────────────────────────────────────────────────
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("Aggregation Level", className="form-label-sm"),
            dcc.RadioItems(
                id="evo-spatial",
                options=[{"label": " Country", "value": "c"},
                         {"label": " Zone",    "value": "z"}],
                value="z", inline=True, className="mt-1",
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "12px", "fontSize": "0.85rem"},
            ),
        ], md=2),
        dbc.Col([
            html.Label("Zone / Country", className="form-label-sm"),
            dcc.Dropdown(id="evo-zones", multi=True, placeholder="All (aggregated)",
                         style={"fontSize": "0.85rem"}),
        ], md=3),
        dbc.Col([
            html.Label("Years", className="form-label-sm"),
            dcc.Dropdown(id="evo-years", multi=True, placeholder="All years",
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Legend filter", className="form-label-sm"),
            dcc.Dropdown(id="evo-legend-filter", multi=True,
                         placeholder="All categories",
                         style={"fontSize": "0.85rem"}),
        ], md=3),
        dbc.Col(md=2),
    ], className="g-2")), className="mb-2 shadow-sm filter-card"),

    # ── Filter strip row 3 (line overlay) ─────────────────────────────────
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("Line Overlay", className="form-label-sm"),
            dcc.Dropdown(
                id="evo-line-indicator",
                options=loader.LINE_INDICATOR_OPTIONS,
                value="",
                clearable=False,
                style={"fontSize": "0.85rem"},
            ),
        ], md=4),
    ], className="g-2")), className="mb-3 shadow-sm filter-card"),

    # ── Main chart ────────────────────────────────────────────────────────
    dbc.Card([
        dbc.CardBody(dcc.Graph(
            id="evo-chart",
            config={"displayModeBar": True,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
            style={"height": "580px"},
        )),
    ], className="shadow-sm"),
], fluid=True, className="py-3 px-4")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("evo-ref-scenario",  "options"),
    Output("evo-ref-scenario",  "value"),
    Output("evo-scenarios",     "options"),
    Output("evo-scenarios",     "value"),
    Output("evo-years",         "options"),
    Output("evo-zones",         "options"),
    Output("evo-legend-filter", "options"),
    Input("global-store",       "data"),
    Input("evo-spatial",        "value"),
    Input("evo-indicator",      "value"),
)
def init_evo_dropdowns(store, spatial, indicator):
    mt, reg = store["model_type"], store["region"]
    scenarios = loader.get_scenarios(mt, reg)
    years     = loader.get_years(mt, reg)
    s_opts = [{"label": s, "value": s} for s in scenarios]
    y_opts = [{"label": str(int(y)), "value": y} for y in years]

    units = loader.get_zones(mt, reg) if spatial == "z" else loader.get_countries(mt, reg)
    u_opts = [{"label": u, "value": u} for u in units]

    src, legend_col = loader.INDICATOR_SOURCE.get(indicator, ("techfuel", "techfuel"))
    if src == "techfuel":
        df = loader.load_techfuel(mt, reg)
    elif src == "costs":
        df = loader.load_costs(mt, reg)
    else:
        df = loader.load_capex(mt, reg)

    leg_opts = []
    if not df.empty and legend_col in df.columns:
        cats = sorted(df[legend_col].dropna().unique().tolist())
        leg_opts = [{"label": c, "value": c} for c in cats]

    default_ref = "baseline" if "baseline" in scenarios else (scenarios[0] if scenarios else None)
    return (s_opts, default_ref,
            s_opts, scenarios,       # all scenarios selected by default
            y_opts,
            u_opts, leg_opts)


@callback(
    Output("evo-chart", "figure"),
    Input("evo-indicator",      "value"),
    Input("evo-line-indicator", "value"),
    Input("evo-scenarios",      "value"),
    Input("evo-ref-scenario",   "value"),
    Input("evo-view",           "value"),
    Input("evo-spatial",        "value"),
    Input("evo-zones",          "value"),
    Input("evo-years",          "value"),
    Input("evo-legend-filter",  "value"),
    Input("global-store",       "data"),
)
def update_evolution(indicator, line_ind, scenarios, ref_scenario,
                     view, spatial, zones, years_filter,
                     legend_filter, store):
    empty = go.Figure()
    empty.update_layout(paper_bgcolor="white", plot_bgcolor="white",
                         margin=dict(l=10, r=10, t=50, b=10),
                         annotations=[dict(text="Select an indicator to display",
                                          xref="paper", yref="paper",
                                          x=0.5, y=0.5, showarrow=False,
                                          font=dict(size=14, color="#aaa"))])
    if not indicator:
        return empty

    mt, reg = store["model_type"], store["region"]
    src, legend_col = loader.INDICATOR_SOURCE[indicator]

    if src == "techfuel":
        df = loader.load_techfuel(mt, reg)
    elif src == "costs":
        df = loader.load_costs(mt, reg)
    else:
        df = loader.load_capex(mt, reg)

    if df.empty:
        return empty

    df = df[df["attribute"] == indicator].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["value"])

    # Scenario filter
    if scenarios:
        df = df[df["scenario"].isin(scenarios)]

    # Year filter
    if years_filter:
        df = df[df["y"].isin(years_filter)]

    # Zone filter
    if zones:
        df = df[df[spatial].isin(zones)]

    # Legend filter
    if legend_filter:
        df = df[df[legend_col].isin(legend_filter)]

    # Aggregate across zones → one value per (scenario, year, legend)
    group_cols = ["scenario", "y", legend_col]
    df_agg = df.groupby(group_cols, as_index=False)["value"].sum()

    if df_agg.empty:
        return empty

    # ── Apply view mode ───────────────────────────────────────────────────
    if view == "Difference":
        df_ref = df_agg[df_agg["scenario"] == ref_scenario][["y", legend_col, "value"]].copy()
        df_ref = df_ref.rename(columns={"value": "ref_value"})
        df_agg = df_agg.merge(df_ref, on=["y", legend_col], how="left")
        df_agg["ref_value"] = df_agg["ref_value"].fillna(0)
        df_agg["value"] = df_agg["value"] - df_agg["ref_value"]
        df_agg = df_agg.drop(columns=["ref_value"])
        # In Difference mode, reference scenario always shows 0 → don't display it
        df_agg = df_agg[df_agg["scenario"] != ref_scenario]

    elif view == "Percentage":
        # Tableau: SUM(value) / TOTAL(SUM(value)) — share of total per (year, scenario)
        totals = df_agg.groupby(["scenario", "y"])["value"].transform("sum")
        df_agg["value"] = np.where(
            totals != 0,
            df_agg["value"] / totals * 100,
            0,
        )

    # Drop truly zero-value rows (invisible bars, reduce noise)
    df_agg = df_agg[df_agg["value"].abs() > 1e-6]
    if df_agg.empty:
        return empty

    # ── Build x-axis: Year × Scenario grouped ────────────────────────────
    years_list = sorted(df_agg["y"].unique().tolist())
    # baseline first, then others alphabetically
    all_s = sorted(df_agg["scenario"].unique().tolist())
    scenarios_list = (["baseline"] if "baseline" in all_s else []) + \
                     [s for s in all_s if s != "baseline"]
    n_s = len(scenarios_list)
    n_y = len(years_list)
    n_total = n_s * n_y

    df_agg["x_label"] = (
        df_agg["y"].astype(int).astype(str) + " | " + df_agg["scenario"]
    )
    x_order = [f"{int(y)} | {s}" for y in years_list for s in scenarios_list]

    # Tech/legend ordering
    cats = df_agg[legend_col].unique().tolist()
    ordered_cats = [t for t in loader.TECH_ORDER if t in cats] + \
                   [t for t in cats if t not in loader.TECH_ORDER]

    # ── Plotly bar chart ──────────────────────────────────────────────────
    # Use "relative" for Difference (handles negative stacks), "stack" otherwise
    bar_mode = "relative" if view == "Difference" else "stack"

    fig = go.Figure()

    for cat in ordered_cats:
        cat_df = df_agg[df_agg[legend_col] == cat].copy()
        if cat_df.empty:
            continue
        color = loader.TECH_COLORS.get(cat, "#aaaaaa")
        fig.add_trace(go.Bar(
            x=cat_df["x_label"],
            y=cat_df["value"],
            name=cat,
            marker_color=color,
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"<b>{cat}</b>: %{{y:,.1f}}<extra></extra>"
            ),
            legendgroup=cat,
        ))

    fig.update_layout(barmode=bar_mode)

    # Apply category order on x-axis
    # Filter x_order to only those that appear in the data
    x_order_filtered = [x for x in x_order if x in df_agg["x_label"].values]
    fig.update_xaxes(
        categoryorder="array",
        categoryarray=x_order_filtered,
    )

    # ── Year group separators + labels ────────────────────────────────────
    # Tick labels: show only scenario name (year shown via annotation)
    tick_labels = [f"{s}" for y in years_list for s in scenarios_list
                   if f"{int(y)} | {s}" in x_order_filtered]
    tick_vals   = [x for x in x_order_filtered]

    # Calculate positions for year annotations and separators
    # Based on actual x_order_filtered positions
    pos_map = {x: i for i, x in enumerate(x_order_filtered)}
    n_total_actual = len(x_order_filtered)

    for i_y, y in enumerate(years_list):
        y_positions = [pos_map[x] for x in x_order_filtered
                       if x.startswith(f"{int(y)} | ")]
        if not y_positions:
            continue
        # Separator before year group (except first)
        if i_y > 0 and y_positions:
            fig.add_shape(
                type="line",
                x0=y_positions[0] - 0.5, x1=y_positions[0] - 0.5, y0=0, y1=1.0,
                xref="x", yref="paper",
                line=dict(color="#aaaaaa", width=1.5, dash="dot"),
            )
        # Year annotation above group
        fig.add_annotation(
            x=np.mean(y_positions), y=1.04, xref="x", yref="paper",
            text=f"<b>{int(y)}</b>",
            showarrow=False,
            font=dict(size=12, color="#1B2A4A"),
            xanchor="center",
        )

    fig.update_xaxes(
        ticktext=tick_labels,
        tickvals=tick_vals,
        tickangle=-30,
        tickfont=dict(size=10),
    )

    # ── Y-axis label ──────────────────────────────────────────────────────
    y_label = loader.INDICATOR_LABELS.get(indicator, indicator)
    if view == "Difference":
        y_label = f"Δ {y_label} vs {ref_scenario}"
    elif view == "Percentage":
        y_label = "Share (%)"

    # ── Total dot: always shown, hover only (no text label) ──────────────
    bar_totals = (
        df_agg
        .groupby("x_label")["value"]
        .sum()
        .reindex(x_order_filtered)
        .dropna()
    )
    if not bar_totals.empty:
        fig.add_trace(go.Scatter(
            x=bar_totals.index.tolist(),
            y=bar_totals.values.tolist(),
            mode="markers",
            marker=dict(color="#1B2A4A", size=9, symbol="diamond",
                        line=dict(color="white", width=1.5)),
            name="Total",
            hovertemplate="<b>Total</b> %{x}: %{y:,.0f}<extra></extra>",
            showlegend=True,
        ))

    fig.update_layout(
        margin=dict(l=10, r=20, t=55, b=60),
        legend=dict(
            orientation="v", x=1.01, y=1,
            font=dict(size=10), title=dict(text=""),
        ),
        yaxis_title=y_label,
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(size=11),
        hovermode="closest",
        bargap=0.2,
    )

    # ── Line overlay (secondary y-axis) ───────────────────────────────────
    if line_ind:
        yz = loader.load_yearly_zone(mt, reg)
        yz_sub = yz[(yz["attribute"] == line_ind)].copy()
        if zones:
            yz_sub = yz_sub[yz_sub[spatial].isin(zones)]
        if scenarios:
            yz_sub = yz_sub[yz_sub["scenario"].isin(scenarios)]
        if years_filter:
            yz_sub = yz_sub[yz_sub["y"].isin(years_filter)]
        yz_line = yz_sub.groupby(["scenario", "y"], as_index=False)["value"].sum()

        for scen in scenarios_list:
            s_line = yz_line[yz_line["scenario"] == scen].sort_values("y")
            s_line = s_line[s_line["y"].isin(years_list)].copy()
            s_line["x_label"] = s_line["y"].astype(int).astype(str) + " | " + scen
            # Keep only x_labels that are in our filtered order
            s_line = s_line[s_line["x_label"].isin(x_order_filtered)]
            if not s_line.empty:
                fig.add_trace(go.Scatter(
                    x=s_line["x_label"],
                    y=s_line["value"],
                    name=f"{loader.INDICATOR_LABELS.get(line_ind, line_ind)} ({scen})",
                    yaxis="y2",
                    mode="lines+markers",
                    line=dict(width=2, dash="dash"),
                    marker=dict(size=6),
                    hovertemplate=(
                        f"<b>{scen}</b><br>"
                        f"{loader.INDICATOR_LABELS.get(line_ind, line_ind)}: "
                        "%{y:,.1f}<extra></extra>"
                    ),
                ))

        fig.update_layout(
            yaxis2=dict(
                title=loader.INDICATOR_LABELS.get(line_ind, line_ind),
                overlaying="y", side="right", showgrid=False,
            )
        )

    return fig
