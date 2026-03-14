import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, callback
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from data import loader

dash.register_page(__name__, path="/", name="Overview", order=0)

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def kpi_card(title, value_id, icon, color):
    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.I(className=f"bi {icon}", style={"fontSize": "2rem", "color": color}), width=3),
                dbc.Col([
                    html.P(title, className="text-muted mb-0", style={"fontSize": "0.78rem", "fontWeight": 600}),
                    html.H4(id=value_id, className="mb-0 fw-bold"),
                ], width=9),
            ], align="center"),
        ])
    ], className="shadow-sm h-100")


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

layout = dbc.Container([
    # ── Filter strip ─────────────────────────────────────────────────────
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("Scenario", className="form-label-sm"),
            dcc.Dropdown(id="ov-scenario", clearable=False, style={"fontSize": "0.85rem"}),
        ], md=3),
        dbc.Col([
            html.Label("Year", className="form-label-sm"),
            dcc.Dropdown(id="ov-year", clearable=False, style={"fontSize": "0.85rem"}),
        ], md=2),
    ], className="g-2")), className="mb-3 shadow-sm filter-card"),

    # ── KPI strip ────────────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(kpi_card("System NPV Cost",    "ov-kpi-npv",      "bi-currency-dollar",   "#2c6fad"), md=3),
        dbc.Col(kpi_card("Total Capacity",     "ov-kpi-capa",     "bi-lightning-charge",  "#2d9e4f"), md=3),
        dbc.Col(kpi_card("Total Demand",       "ov-kpi-demand",   "bi-graph-up",          "#f77f00"), md=3),
        dbc.Col(kpi_card("Total Emissions",    "ov-kpi-co2",      "bi-cloud-haze2",       "#d62728"), md=3),
    ], className="mb-3 g-3"),

    # ── Map + Capacity bar ───────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("Installed Capacity by Country")),
            dbc.CardBody(dcc.Graph(id="ov-map", config={"displayModeBar": False},
                                   style={"height": "340px"})),
        ], className="shadow-sm"), md=5),
        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("Capacity Mix — Selected Year")),
            dbc.CardBody(dcc.Graph(id="ov-capacity-bar", config={"displayModeBar": False},
                                   style={"height": "340px"})),
        ], className="shadow-sm"), md=7),
    ], className="mb-3 g-3"),

    # ── Utilization + Price ──────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("Interconnection Utilization Rate")),
            dbc.CardBody(dcc.Graph(id="ov-utilization", config={"displayModeBar": False},
                                   style={"height": "300px"})),
        ], className="shadow-sm"), md=7),
        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("Average Electricity Price (USD/MWh)")),
            dbc.CardBody(dcc.Graph(id="ov-price", config={"displayModeBar": False},
                                   style={"height": "300px"})),
        ], className="shadow-sm"), md=5),
    ], className="mb-3 g-3"),
], fluid=True, className="py-3 px-4")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("ov-scenario", "options"),
    Output("ov-scenario", "value"),
    Output("ov-year",     "options"),
    Output("ov-year",     "value"),
    Input("global-store", "data"),
)
def init_filters(store):
    mt, reg = store["model_type"], store["region"]
    scenarios = loader.get_scenarios(mt, reg)
    years     = loader.get_years(mt, reg)
    s_opts = [{"label": s, "value": s} for s in scenarios]
    y_opts = [{"label": str(int(y)), "value": y} for y in years]
    return s_opts, (scenarios[0] if scenarios else None), y_opts, (years[-1] if years else None)


@callback(
    Output("ov-kpi-npv",    "children"),
    Output("ov-kpi-capa",   "children"),
    Output("ov-kpi-demand", "children"),
    Output("ov-kpi-co2",    "children"),
    Input("ov-scenario", "value"),
    Input("global-store", "data"),
)
def update_kpis(scenario, store):
    if not scenario:
        return "—", "—", "—", "—"
    mt, reg = store["model_type"], store["region"]

    # NPV system cost
    npv_df = loader.load_npv(mt, reg)
    npv_val = "—"
    if not npv_df.empty:
        row = npv_df[(npv_df["attribute"] == "NetPresentCostSystem") &
                     (npv_df["uni"] == "NPV of system cost: $m")]
        if not row.empty:
            v = pd.to_numeric(row["value"].iloc[0], errors="coerce")
            npv_val = f"${v/1000:.1f}B" if pd.notna(v) else "—"

    # Total capacity (latest year)
    tf = loader.load_techfuel(mt, reg)
    capa_val = "—"
    if not tf.empty:
        sub = tf[(tf["scenario"] == scenario) & (tf["attribute"] == "CapacityTechFuel")]
        if not sub.empty:
            latest = sub["y"].max()
            total_mw = sub[sub["y"] == latest]["value"].sum()
            capa_val = f"{total_mw/1000:.1f} GW"

    # Demand & CO2 (latest year)
    yz = loader.load_yearly_zone(mt, reg)
    demand_val, co2_val = "—", "—"
    if not yz.empty:
        sub = yz[yz["scenario"] == scenario]
        latest = sub["y"].max()
        sub_latest = sub[sub["y"] == latest]

        dem = sub_latest[sub_latest["attribute"] == "DemandEnergyZone"]["value"].sum()
        co2 = sub_latest[sub_latest["attribute"] == "EmissionsZone"]["value"].sum()
        demand_val = f"{dem/1000:.1f} TWh" if dem > 0 else "—"
        co2_val    = f"{co2:.1f} MtCO₂"   if co2 > 0 else "—"

    return npv_val, capa_val, demand_val, co2_val


@callback(
    Output("ov-map",          "figure"),
    Output("ov-capacity-bar", "figure"),
    Input("ov-scenario", "value"),
    Input("ov-year",     "value"),
    Input("global-store", "data"),
)
def update_map_and_capacity(scenario, year, store):
    empty_fig = go.Figure()
    empty_fig.update_layout(paper_bgcolor="white", plot_bgcolor="white",
                             margin=dict(l=0, r=0, t=0, b=0))
    if not scenario or not year:
        return empty_fig, empty_fig

    mt, reg = store["model_type"], store["region"]
    tf = loader.load_techfuel(mt, reg)
    if tf.empty:
        return empty_fig, empty_fig

    sub = tf[(tf["scenario"] == scenario) &
             (tf["attribute"] == "CapacityTechFuel") &
             (tf["y"] == year)]

    # ── Map ──────────────────────────────────────────────────────────────
    country_totals = sub.groupby("c", as_index=False)["value"].sum()
    country_totals["iso"] = country_totals["c"].map(loader.COUNTRY_ISO)
    country_totals["label"] = country_totals["value"].apply(lambda v: f"{v/1000:.1f} GW")

    map_fig = go.Figure(go.Choropleth(
        locations=country_totals["iso"],
        z=country_totals["value"] / 1000,
        text=country_totals["c"],
        customdata=country_totals["label"],
        hovertemplate="<b>%{text}</b><br>Capacity: %{customdata}<extra></extra>",
        colorscale="Blues",
        colorbar=dict(title="GW", thickness=12, len=0.7),
        marker_line_color="white",
        marker_line_width=0.5,
    ))
    map_fig.update_geos(
        scope="africa", showcoastlines=True, coastlinecolor="lightgrey",
        showland=True, landcolor="#f8f9fa",
        showframe=False, projection_type="mercator",
        fitbounds="locations",
    )
    map_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="white", geo_bgcolor="white",
    )

    # ── Capacity stacked bar ─────────────────────────────────────────────
    tech_order = [t for t in loader.TECH_ORDER if t in sub["techfuel"].unique()]
    other = [t for t in sub["techfuel"].unique() if t not in tech_order]
    tech_order = other + tech_order

    pivot = sub.groupby(["z", "techfuel"])["value"].sum().reset_index()
    bar_fig = px.bar(
        pivot, x="z", y="value", color="techfuel",
        color_discrete_map=loader.TECH_COLORS,
        category_orders={"techfuel": tech_order},
        labels={"value": "Capacity (MW)", "z": "Zone", "techfuel": "Technology"},
        template="plotly_white",
    )
    bar_fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=40),
        legend=dict(orientation="v", x=1.01, y=1, font=dict(size=10)),
        xaxis_tickangle=-30,
        yaxis_title="Capacity (MW)",
        plot_bgcolor="white", paper_bgcolor="white",
    )
    return map_fig, bar_fig


@callback(
    Output("ov-utilization", "figure"),
    Input("ov-scenario", "value"),
    Input("global-store", "data"),
)
def update_utilization(scenario, store):
    empty = go.Figure()
    empty.update_layout(paper_bgcolor="white", plot_bgcolor="white",
                         margin=dict(l=0, r=0, t=0, b=0))
    if not scenario:
        return empty

    mt, reg = store["model_type"], store["region"]
    tr = loader.load_transmission(mt, reg)
    if tr.empty:
        return empty

    sub = tr[(tr["scenario"] == scenario) & (tr["attribute"] == "InterconUtilization")]
    sub = sub.dropna(subset=["value"])
    if sub.empty:
        return empty

    sub["corridor"] = sub["z"] + " → " + sub["z2"]
    pivot = sub.pivot_table(index="corridor", columns="y", values="value", aggfunc="mean")
    pivot = pivot.fillna(0) * 100  # to %

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[str(int(c)) for c in pivot.columns],
        y=pivot.index.tolist(),
        colorscale="YlOrRd",
        zmin=0, zmax=100,
        hovertemplate="<b>%{y}</b><br>Year: %{x}<br>Utilization: %{z:.1f}%<extra></extra>",
        colorbar=dict(title="%", thickness=12),
    ))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis_title="Year", yaxis_title="",
        font=dict(size=11),
    )
    return fig


@callback(
    Output("ov-price", "figure"),
    Input("ov-scenario", "value"),
    Input("ov-year",     "value"),
    Input("global-store", "data"),
)
def update_price(scenario, year, store):
    empty = go.Figure()
    empty.update_layout(paper_bgcolor="white", plot_bgcolor="white",
                         margin=dict(l=0, r=0, t=0, b=0))
    if not scenario or not year:
        return empty

    mt, reg = store["model_type"], store["region"]
    yz = loader.load_yearly_zone(mt, reg)
    if yz.empty:
        return empty

    sub = yz[(yz["scenario"] == scenario) &
             (yz["attribute"] == "GenCostsPerMWh") &
             (yz["y"] == year)].dropna(subset=["value"])
    if sub.empty:
        return empty

    sub_sorted = sub.sort_values("value", ascending=True)
    fig = go.Figure(go.Bar(
        x=sub_sorted["value"],
        y=sub_sorted["z"],
        orientation="h",
        marker_color="#2c6fad",
        hovertemplate="<b>%{y}</b><br>%{x:.1f} USD/MWh<extra></extra>",
    ))
    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        paper_bgcolor="white", plot_bgcolor="white",
        xaxis_title="USD/MWh", yaxis_title="",
        font=dict(size=11),
    )
    return fig
