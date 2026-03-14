import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, ctx, no_update
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from data import loader

dash.register_page(__name__, path="/power-plants", name="Power Plants", order=4)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dbc.Container([
    # ── Filter strip ─────────────────────────────────────────────────────
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("Scenario", className="form-label-sm"),
            dcc.Dropdown(id="pp-scenario", clearable=False,
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Year", className="form-label-sm"),
            dcc.Dropdown(id="pp-year", clearable=False,
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Spatial Resolution", className="form-label-sm"),
            dcc.RadioItems(
                id="pp-spatial",
                options=[{"label": " Country", "value": "c"},
                         {"label": " Zone",    "value": "z"}],
                value="z", inline=True, className="mt-1",
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "12px", "fontSize": "0.85rem"},
            ),
        ], md=2),
        dbc.Col([
            html.Label("Zone / Country", className="form-label-sm"),
            dcc.Dropdown(id="pp-zone", multi=True, placeholder="All zones",
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Plant Indicator", className="form-label-sm"),
            dcc.Dropdown(
                id="pp-indicator",
                options=loader.PLANT_INDICATOR_OPTIONS,
                value="CapacityPlant",
                clearable=False,
                style={"fontSize": "0.85rem"},
            ),
        ], md=2),
        dbc.Col([
            html.Label("Top N plants", className="form-label-sm"),
            dcc.Slider(id="pp-topn", min=10, max=50, step=5, value=25,
                       marks={10: "10", 25: "25", 50: "50"},
                       tooltip={"placement": "bottom", "always_visible": False}),
        ], md=2),
    ], className="g-2")), className="mb-3 shadow-sm filter-card"),

    # ── Charts side by side ───────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("Plant Ranking")),
            dbc.CardBody(dcc.Graph(
                id="pp-bar",
                config={"displayModeBar": False},
                style={"height": "540px"},
            )),
        ], className="shadow-sm"), md=6),

        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("LCOE vs Utilization Factor")),
            dbc.CardBody(dcc.Graph(
                id="pp-scatter",
                config={"displayModeBar": True,
                        "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
                style={"height": "540px"},
            )),
        ], className="shadow-sm"), md=6),
    ], className="g-3"),
], fluid=True, className="py-3 px-4")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("pp-scenario", "options"),
    Output("pp-scenario", "value"),
    Output("pp-year",     "options"),
    Output("pp-year",     "value"),
    Input("global-store", "data"),
)
def init_pp_filters(store):
    mt, reg = store["model_type"], store["region"]
    scenarios = loader.get_scenarios(mt, reg)
    years     = loader.get_years(mt, reg)
    s_opts = [{"label": s, "value": s} for s in scenarios]
    y_opts = [{"label": str(int(y)), "value": y} for y in years]
    default_s = "baseline" if "baseline" in scenarios else (scenarios[0] if scenarios else None)
    return s_opts, default_s, y_opts, (years[-1] if years else None)


@callback(
    Output("pp-zone",  "options"),
    Output("pp-zone",  "value"),
    Input("pp-spatial",  "value"),
    Input("global-store","data"),
    State("pp-zone",     "value"),
)
def update_pp_zones(spatial, store, current_value):
    mt, reg = store["model_type"], store["region"]
    units = loader.get_zones(mt, reg) if spatial == "z" else loader.get_countries(mt, reg)
    opts = [{"label": u, "value": u} for u in units]
    # Reset only when spatial resolution changes; preserve selection on store refresh
    if ctx.triggered_id == "pp-spatial":
        return opts, None
    valid = set(units)
    if not current_value:
        return opts, no_update
    kept = [v for v in current_value if v in valid] if isinstance(current_value, list) else (current_value if current_value in valid else None)
    return opts, kept


@callback(
    Output("pp-bar",     "figure"),
    Output("pp-scatter", "figure"),
    Input("pp-scenario", "value"),
    Input("pp-year",     "value"),
    Input("pp-spatial",  "value"),
    Input("pp-zone",     "value"),
    Input("pp-indicator","value"),
    Input("pp-topn",     "value"),
    Input("global-store","data"),
)
def update_pp_charts(scenario, year, spatial, zone, indicator, topn, store):
    empty = go.Figure()
    empty.update_layout(paper_bgcolor="white", plot_bgcolor="white",
                         margin=dict(l=10, r=10, t=10, b=10))
    if not all([scenario, year]):
        return empty, empty

    mt, reg = store["model_type"], store["region"]
    df = loader.load_plants(mt, reg)
    if df.empty:
        return empty, empty

    spatial_col = "z" if spatial == "z" else "c"
    df_sel = df[(df["scenario"] == scenario) & (df["y"] == year)].copy()
    if zone:
        df_sel = df_sel[df_sel[spatial_col].isin(zone if isinstance(zone, list) else [zone])]
    df_sel["value"] = pd.to_numeric(df_sel["value"], errors="coerce")
    df_sel = df_sel.dropna(subset=["value"])

    # ── Bar chart: Plant ranking ─────────────────────────────────────────
    ind_df = df_sel[df_sel["attribute"] == indicator].copy()
    ind_df = ind_df[ind_df["value"] > 0]
    if ind_df.empty:
        bar_fig = empty
    else:
        ind_df = ind_df.nlargest(topn, "value")
        ind_df = ind_df.sort_values("value", ascending=True)
        label = next((o["label"] for o in loader.PLANT_INDICATOR_OPTIONS
                      if o["value"] == indicator), indicator)
        bar_fig = px.bar(
            ind_df, x="value", y="g", color="techfuel",
            orientation="h",
            color_discrete_map=loader.TECH_COLORS,
            labels={"value": label, "g": "Plant", "techfuel": "Technology"},
            template="plotly_white",
        )
        bar_fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=20),
            legend=dict(orientation="v", x=1.01, y=1, font=dict(size=9)),
            xaxis_title=label, yaxis_title="",
            plot_bgcolor="white", paper_bgcolor="white",
            font=dict(size=10),
        )
        bar_fig.update_yaxes(tickfont=dict(size=9))

    # ── Scatter: LCOE vs Utilization ─────────────────────────────────────
    lcoe_df  = df_sel[df_sel["attribute"] == "PlantAnnualLCOE"].rename(columns={"value": "lcoe"})
    util_df  = df_sel[df_sel["attribute"] == "UtilizationPlant"].rename(columns={"value": "util"})
    capa_df  = df_sel[df_sel["attribute"] == "CapacityPlant"].rename(columns={"value": "capa"})

    merge_keys = ["g", "techfuel", "tech", "f"]
    present_keys = [k for k in merge_keys if k in lcoe_df.columns and k in util_df.columns]

    scatter_fig = empty
    if not lcoe_df.empty and not util_df.empty:
        scatter = lcoe_df[present_keys + ["lcoe"]].merge(
            util_df[present_keys + ["util"]], on=present_keys, how="inner")
        if not capa_df.empty:
            scatter = scatter.merge(capa_df[present_keys + ["capa"]], on=present_keys, how="left")
        else:
            scatter["capa"] = 10

        scatter = scatter.dropna(subset=["lcoe", "util"])
        if not scatter.empty:
            scatter_fig = px.scatter(
                scatter, x="util", y="lcoe",
                color="techfuel", size="capa",
                size_max=40,
                hover_name="g",
                color_discrete_map=loader.TECH_COLORS,
                labels={"util": "Utilization Factor",
                        "lcoe": "LCOE (USD/MWh)", "techfuel": "Technology"},
                template="plotly_white",
            )
            scatter_fig.update_layout(
                margin=dict(l=10, r=20, t=10, b=20),
                legend=dict(orientation="v", x=1.01, y=1, font=dict(size=10)),
                xaxis_title="Utilization Factor",
                yaxis_title="LCOE (USD/MWh)",
                plot_bgcolor="white", paper_bgcolor="white",
                font=dict(size=11),
            )

    return bar_fig, scatter_fig
