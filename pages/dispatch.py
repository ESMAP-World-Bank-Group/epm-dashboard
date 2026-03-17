import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, ctx, no_update
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import numpy as np
from data import loader

dash.register_page(__name__, path="/dispatch", name="Dispatch", order=3)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dbc.Container([
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("Scenario", className="form-label-sm"),
            dcc.Dropdown(id="dp-scenario", multi=True, placeholder="Select scenario(s)",
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Spatial Resolution", className="form-label-sm"),
            dcc.RadioItems(
                id="dp-spatial",
                options=[{"label": " Country", "value": "c"},
                         {"label": " Zone",    "value": "z"}],
                value="z", inline=True, className="mt-1",
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "12px", "fontSize": "0.85rem"},
            ),
        ], md=2),
        dbc.Col([
            html.Label("Zone / Country", className="form-label-sm"),
            dcc.Dropdown(id="dp-zone", clearable=False, style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Year", className="form-label-sm"),
            dcc.Dropdown(id="dp-year", clearable=False, style={"fontSize": "0.85rem"}),
        ], md=1),
        dbc.Col([
            html.Label("View", className="form-label-sm"),
            dcc.RadioItems(
                id="dp-view",
                options=[{"label": " Single Day",  "value": "single"},
                         {"label": " Full Year",   "value": "full"},
                         {"label": " Difference",  "value": "diff"}],
                value="single", inline=True, className="mt-1",
                inputStyle={"marginRight": "4px"},
                labelStyle={"marginRight": "10px", "fontSize": "0.85rem"},
            ),
        ], md=3),
        dbc.Col([
            html.Label("Quarter", className="form-label-sm"),
            dcc.Dropdown(id="dp-quarter", clearable=False, style={"fontSize": "0.85rem"}),
        ], md=1),
        dbc.Col([
            html.Label("Day Type", className="form-label-sm"),
            dcc.Dropdown(id="dp-day", clearable=False, style={"fontSize": "0.85rem"}),
        ], md=1),
    ], className="g-2")), className="mb-2 shadow-sm filter-card"),

    dbc.Row([
        dbc.Col(
            dbc.Button("Load Dispatch Data", id="dp-load-btn", color="primary",
                       size="sm", className="me-2"),
            width="auto",
        ),
        dbc.Col(
            html.Span(id="dp-status", className="text-muted",
                      style={"fontSize": "0.82rem", "lineHeight": "31px"}),
            width="auto",
        ),
    ], className="mb-3 align-items-center"),

    dbc.Card(dbc.CardBody(
        dcc.Graph(id="dp-chart",
                  config={"displayModeBar": True,
                          "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
                  style={"width": "100%"}),
    ), className="shadow-sm mb-3"),

    dbc.Card([
        dbc.CardHeader(html.B("Hourly Electricity Price (USD/MWh)")),
        dbc.CardBody(dcc.Graph(id="dp-price-chart",
                               config={"displayModeBar": False},
                               style={"height": "200px"})),
    ], className="shadow-sm"),

    dcc.Store(id="dp-data-store"),
], fluid=True, className="py-3 px-4")


# ---------------------------------------------------------------------------
# Callbacks — filters
# ---------------------------------------------------------------------------

@callback(
    Output("dp-scenario", "options"),
    Output("dp-scenario", "value"),
    Output("dp-year",     "options"),
    Output("dp-year",     "value"),
    Input("global-store", "data"),
)
def init_dp_scenario_year(store):
    mt, reg = store["model_type"], store["region"]
    scenarios = loader.get_scenarios(mt, reg)
    years     = loader.get_years(mt, reg)
    s_opts = [{"label": s, "value": s} for s in scenarios]
    y_opts = [{"label": str(int(y)), "value": y} for y in years]
    default_s = ["baseline"] if "baseline" in scenarios else ([scenarios[0]] if scenarios else [])
    return s_opts, default_s, y_opts, (years[0] if years else None)


@callback(
    Output("dp-zone", "options"),
    Output("dp-zone", "value"),
    Input("dp-spatial",   "value"),
    Input("global-store", "data"),
    State("dp-zone",      "value"),
)
def update_dp_zones(spatial, store, current_value):
    mt, reg = store["model_type"], store["region"]
    units = loader.get_zones(mt, reg) if spatial == "z" else loader.get_countries(mt, reg)
    opts = [{"label": u, "value": u} for u in units]
    # Reset only when spatial resolution changes; preserve selection on store refresh
    if ctx.triggered_id == "dp-spatial":
        return opts, (units[0] if units else None)
    if current_value and current_value in set(units):
        return opts, no_update
    return opts, (units[0] if units else None)


@callback(
    Output("dp-data-store", "data"),
    Output("dp-status",     "children"),
    Output("dp-quarter",    "options"),
    Output("dp-quarter",    "value"),
    Output("dp-day",        "options"),
    Output("dp-day",        "value"),
    Input("dp-load-btn",    "n_clicks"),
    State("dp-scenario",    "value"),
    State("dp-year",        "value"),
    State("dp-spatial",     "value"),
    State("dp-zone",        "value"),
    State("global-store",   "data"),
    prevent_initial_call=True,
)
def load_dp_data(n, scenarios, year, spatial, zone, store):
    empty = []
    if not scenarios or not year or not zone:
        return None, "Select filters first.", empty, None, empty, None

    active = scenarios if isinstance(scenarios, list) else [scenarios]
    mt, reg = store["model_type"], store["region"]
    df = loader.load_dispatch(mt, reg)
    if df.empty:
        return None, "No dispatch data found.", empty, None, empty, None

    spatial_col = "z" if spatial == "z" else "c"
    df = df[(df[spatial_col] == zone) &
            (df["y"] == year) &
            (df["scenario"].isin(active))].copy()

    if df.empty:
        return None, "No data for this selection.", empty, None, empty, None

    quarters = sorted(df["q"].dropna().unique())
    days     = sorted(df["d"].dropna().unique())
    q_opts = [{"label": q, "value": q} for q in quarters]
    d_opts = [{"label": d, "value": d} for d in days]

    # Store only metadata — avoids large JSON payload in dcc.Store
    import json as _json
    meta = {"zone": zone, "year": year, "scenarios": active,
            "spatial": spatial, "mt": mt, "reg": reg}
    status = f"Loaded — {zone} / {', '.join(active)} / {int(year)}"
    return _json.dumps(meta), status, q_opts, quarters[0], d_opts, days[0]


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _parse(df):
    df = df.copy()
    df["t_num"] = df["t"].str.extract(r"(\d+)").astype(int)
    df["q_num"] = df["q"].str.extract(r"(\d+)").astype(int)
    df["d_num"] = df["d"].str.extract(r"(\d+)").astype(int)
    return df


def _time_index(df):
    """Build global x index from parsed df (needs q_num, d_num, t_num, q, d)."""
    ti = (df[["q_num", "d_num", "t_num", "q", "d"]]
          .drop_duplicates()
          .sort_values(["q_num", "d_num", "t_num"])
          .reset_index(drop=True))
    ti["x"] = ti.index
    return ti


def _add_row(fig, df, ti, row, legend_shown):
    """Add stacked area traces (pos & neg) for one scenario/row."""
    df = df.merge(ti[["q_num", "d_num", "t_num", "x"]], on=["q_num", "d_num", "t_num"])
    x_arr = ti["x"].values

    gen_df    = df[df["uni"] != "Demand"]
    demand_df = df[df["uni"] == "Demand"]

    techs = gen_df["uni"].unique().tolist()
    ordered = [t for t in loader.TECH_ORDER if t in techs] + \
              [t for t in techs if t not in loader.TECH_ORDER]

    for tech in ordered:
        vals = (gen_df[gen_df["uni"] == tech]
                .groupby("x")["value"].sum()
                .reindex(x_arr).fillna(0).values)
        color = loader.TECH_COLORS.get(tech, "#aaaaaa")

        for sg, arr, check in (("pos", np.maximum(vals, 0), lambda a: a.max() > 1e-6),
                                ("neg", np.minimum(vals, 0), lambda a: a.min() < -1e-6)):
            if not check(arr):
                continue
            sl = tech not in legend_shown
            legend_shown.add(tech)
            fig.add_trace(go.Scatter(
                x=x_arr, y=arr, name=tech,
                stackgroup=f"{sg}_{row}", mode="none",
                fillcolor=color, legendgroup=tech,
                showlegend=sl,
                hovertemplate=f"<b>{tech}</b><br>%{{y:.1f}} MW<extra></extra>",
            ), row=row, col=1)

    if not demand_df.empty:
        dem = demand_df.groupby("x")["value"].sum().reindex(x_arr).fillna(0)
        sl = "Demand" not in legend_shown
        legend_shown.add("Demand")
        fig.add_trace(go.Scatter(
            x=dem.index, y=dem.values, name="Demand", mode="lines",
            line=dict(color="#e74c3c", width=1.5),
            legendgroup="Demand", showlegend=sl,
            hovertemplate="<b>Demand</b><br>%{y:.1f} MW<extra></extra>",
        ), row=row, col=1)


def _add_price_overlay(fig, price_df, ti, n_rows, row, scenario, zone, year, view, quarter, day):
    """Overlay marginal cost as secondary y-axis on subplot row."""
    if price_df is None or price_df.empty:
        return
    filt = (price_df["scenario"] == scenario) & (price_df["y"] == year)
    if "z" in price_df.columns:
        filt &= (price_df["z"] == zone)
    if view == "single":
        filt &= (price_df["q"] == quarter) & (price_df["d"] == day)
    p = price_df[filt].copy()
    if p.empty:
        return
    p["t_num"] = p["t"].str.extract(r"(\d+)").astype(int)
    p["q_num"] = p["q"].str.extract(r"(\d+)").astype(int)
    p["d_num"] = p["d"].str.extract(r"(\d+)").astype(int)
    if view == "single":
        p = p.sort_values("t_num")
        x_vals = p["t_num"].values
    else:
        p = p.merge(ti[["q_num", "d_num", "t_num", "x"]],
                    on=["q_num", "d_num", "t_num"], how="inner").sort_values("x")
        x_vals = p["x"].values
    if len(x_vals) == 0:
        return

    # Secondary y-axis: n_rows primary axes already allocated (y1..yn), so use y(n+row)
    sec_num    = n_rows + row
    primary_y  = "y" if row == 1 else f"y{row}"
    x_ax       = "x" if row == 1 else f"x{row}"
    p_max      = float(p["value"].max()) if p["value"].max() > 0 else 100

    fig.add_trace(go.Scatter(
        x=x_vals, y=p["value"].values,
        name="Marg. Cost",
        mode="lines",
        xaxis=x_ax,
        yaxis=f"y{sec_num}",
        line=dict(color="#2c3e50", width=1),
        legendgroup="margcost",
        showlegend=(row == 1),
        hovertemplate="<b>Marg. Cost</b>: %{y:.1f} USD/MWh<extra></extra>",
    ))
    fig.update_layout(**{
        f"yaxis{sec_num}": dict(
            title="USD/MWh" if row == n_rows else "",
            overlaying=primary_y,
            anchor=x_ax,
            side="right",
            showgrid=False,
            zeroline=False,
            range=[0, p_max * 1.2],
            tickfont=dict(size=9),
        )
    })


def _year_separators(fig, ti, day_weights=None):
    """Quarter (thin solid) and day (thin dotted) separators with % weight labels."""
    qd = (ti.groupby(["q_num", "d_num", "q", "d"])["x"]
          .agg(x_min="min", x_max="max").reset_index())
    first_q = qd["q_num"].min()
    n_total = len(qd)
    pct_default = 100.0 / n_total if n_total else 0

    for _, r in qd.iterrows():
        first_d_in_q = r["d_num"] == qd[qd["q_num"] == r["q_num"]]["d_num"].min()
        very_first   = (r["q_num"] == first_q and first_d_in_q)

        if not very_first:
            is_q = first_d_in_q
            fig.add_shape(
                type="line",
                x0=r["x_min"] - 0.5, x1=r["x_min"] - 0.5,
                y0=0, y1=1.0, xref="x", yref="paper",
                line=dict(color="#bbbbbb" if is_q else "#e0e0e0",
                          width=1.0  if is_q else 0.5,
                          dash="solid" if is_q else "dot"),
            )
        mid = (r["x_min"] + r["x_max"]) / 2
        fig.add_annotation(
            x=mid, y=1.03, xref="x", yref="paper",
            text=f"<span style='font-size:8px;color:#888'>{r['d']}</span>",
            showarrow=False, xanchor="center", yanchor="bottom",
        )
        pct = day_weights.get((r["q"], r["d"]), pct_default) if day_weights else pct_default
        fig.add_annotation(
            x=mid, y=1.005, xref="x", yref="paper",
            text=f"<span style='font-size:7px;color:#cccccc'>{pct:.1f}%</span>",
            showarrow=False, xanchor="center", yanchor="bottom",
        )

    for q_num in sorted(qd["q_num"].unique()):
        qr = qd[qd["q_num"] == q_num]
        mid = (qr["x_min"].min() + qr["x_max"].max()) / 2
        fig.add_annotation(
            x=mid, y=-0.05, xref="x", yref="paper",
            text=f"<b>{qr.iloc[0]['q']}</b>",
            showarrow=False, font=dict(size=10, color="#555"),
            xanchor="center", yanchor="top",
        )

    tick_vals = [r["x"] for _, r in ti.iterrows() if r["t_num"] % 6 == 1]
    tick_text = [str(r["t_num"]) for _, r in ti.iterrows() if r["t_num"] % 6 == 1]
    fig.update_xaxes(tickvals=tick_vals, ticktext=tick_text, tickfont=dict(size=8))


# ---------------------------------------------------------------------------
# Main chart builder
# ---------------------------------------------------------------------------

def _build_chart(df, scenarios, zone, year, view, quarter=None, day=None, day_weights=None, price_df=None):
    """Build dispatch figure. Returns (dispatch_fig, scenario_list_used)."""
    # Sort: baseline first
    all_s = sorted(df["scenario"].unique())
    scenarios_list = (["baseline"] if "baseline" in all_s else []) + \
                     [s for s in all_s if s != "baseline"]

    # ── Difference mode ───────────────────────────────────────────────────
    if view == "diff":
        if len(scenarios_list) < 2:
            fig = go.Figure()
            fig.add_annotation(text="Select ≥ 2 scenarios for Difference view",
                               xref="paper", yref="paper", x=0.5, y=0.5,
                               showarrow=False, font=dict(size=14))
            fig.update_layout(height=440, paper_bgcolor="white", plot_bgcolor="white")
            return fig, scenarios_list

        ref = scenarios_list[0]
        cmp = scenarios_list[1]

        ref_df = _parse(df[df["scenario"] == ref])
        cmp_df = _parse(df[df["scenario"] == cmp])
        ti = _time_index(ref_df)

        ref_agg = ref_df.groupby(["q_num", "d_num", "t_num", "uni"])["value"].sum().reset_index()
        cmp_agg = cmp_df.groupby(["q_num", "d_num", "t_num", "uni"])["value"].sum().reset_index()
        delta = cmp_agg.merge(ref_agg, on=["q_num", "d_num", "t_num", "uni"],
                              how="outer", suffixes=("", "_ref"))
        delta["value"] = delta["value"].fillna(0) - delta["value_ref"].fillna(0)
        delta = delta.drop(columns=["value_ref"])
        delta = delta.merge(
            ti[["q_num", "d_num", "t_num", "q", "d"]].drop_duplicates(),
            on=["q_num", "d_num", "t_num"])

        fig = make_subplots(rows=1, cols=1)
        _add_row(fig, delta, ti, 1, set())
        _year_separators(fig, ti, day_weights=day_weights)

        fig.update_layout(
            title=dict(text=f"{zone} — Δ Dispatch ({cmp} − {ref}) | {int(year)}",
                       font=dict(size=12), x=0.01),
            margin=dict(l=10, r=20, t=50, b=60),
            xaxis_title="Hours", yaxis_title="MW",
            legend=dict(orientation="v", x=1.01, y=1, font=dict(size=10)),
            plot_bgcolor="white", paper_bgcolor="white",
            hovermode="x unified", height=480,
        )
        return fig, scenarios_list

    # ── Single Day / Full Year ────────────────────────────────────────────
    n = len(scenarios_list)
    subtitles = scenarios_list[:]  # one subtitle per row

    fig = make_subplots(
        rows=n, cols=1,
        shared_xaxes=True,
        vertical_spacing=max(0.04, 0.12 / n),
        subplot_titles=subtitles,
    )

    # Time index from first scenario
    s0 = _parse(df[df["scenario"] == scenarios_list[0]])
    if view == "single":
        s0 = s0[(s0["q"] == quarter) & (s0["d"] == day)]
    ti = _time_index(s0)

    legend_shown = set()
    for i, scenario in enumerate(scenarios_list, 1):
        sdf = _parse(df[df["scenario"] == scenario])
        if view == "single":
            sdf = sdf[(sdf["q"] == quarter) & (sdf["d"] == day)]
        _add_row(fig, sdf, ti, i, legend_shown)
        _add_price_overlay(fig, price_df, ti, n, i, scenario, zone, year, view, quarter, day)

    if view == "full":
        _year_separators(fig, ti, day_weights=day_weights)
        x_title = "Hours"
    else:
        fig.update_xaxes(tickmode="linear", dtick=2)
        x_title = "Hour"

    height = max(440, 420 * n)
    title_suffix = f" | {quarter} | {day}" if view == "single" else ""

    fig.update_layout(
        title=dict(text=f"{zone} — Dispatch | {int(year)}{title_suffix}",
                   font=dict(size=12), x=0.01),
        margin=dict(l=10, r=60 if price_df is not None else 20, t=50, b=60),
        legend=dict(orientation="v", x=1.10 if price_df is not None else 1.01,
                    y=1, font=dict(size=10)),
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified", height=height,
    )
    for i in range(1, n + 1):
        axis = f"yaxis{i}" if i > 1 else "yaxis"
        axis_x = f"xaxis{i}" if i > 1 else "xaxis"
        fig.update_layout(**{axis: dict(title="MW"),
                              axis_x: dict(title=x_title if i == n else "")})

    return fig, scenarios_list


# ---------------------------------------------------------------------------
# Chart callback
# ---------------------------------------------------------------------------

@callback(
    Output("dp-chart",       "figure"),
    Output("dp-price-chart", "figure"),
    Input("dp-data-store",   "data"),
    Input("dp-quarter",      "value"),
    Input("dp-day",          "value"),
    Input("dp-view",         "value"),
    State("dp-year",         "value"),
    State("dp-zone",         "value"),
)
def update_dispatch_chart(data_json, quarter, day, view, year, zone):
    empty = go.Figure()
    empty.update_layout(paper_bgcolor="white", plot_bgcolor="white",
                         margin=dict(l=10, r=10, t=30, b=10), height=440)

    if not data_json:
        return empty, empty
    if view == "single" and (not quarter or not day):
        return empty, empty

    import json as _json
    meta = _json.loads(data_json)
    mt, reg   = meta["mt"], meta["reg"]
    zone      = meta["zone"]
    year      = meta["year"]
    scenarios = meta["scenarios"]
    spatial   = meta["spatial"]
    spatial_col = "z" if spatial == "z" else "c"

    full_df = loader.load_dispatch(mt, reg)
    if full_df.empty:
        return empty, empty
    df = full_df[(full_df[spatial_col] == zone) &
                 (full_df["y"] == year) &
                 (full_df["scenario"].isin(scenarios))].copy()
    day_weights = loader.load_phours(mt, reg)
    price_df    = loader.load_hourly_price(mt, reg)
    dispatch_fig, scenarios_list = _build_chart(
        df, scenarios, zone, year, view, quarter, day,
        day_weights=day_weights,
        price_df=price_df if not price_df.empty else None,
    )

    # ── Price chart (all scenarios overlaid) ─────────────────────────────
    price_df  = loader.load_hourly_price(mt, reg)
    price_fig = go.Figure()

    if not price_df.empty:
        colors = ["#2c6fad", "#e07b39", "#27ae60", "#8e44ad"]
        for i, scenario in enumerate(scenarios_list):
            filt = (price_df["scenario"] == scenario) & (price_df["y"] == year)
            if "z" in price_df.columns:
                filt &= (price_df["z"] == zone)
            if view == "single":
                filt &= (price_df["q"] == quarter) & (price_df["d"] == day)
            p = price_df[filt].copy()
            if p.empty:
                continue
            p["t_num"] = p["t"].str.extract(r"(\d+)").astype(int)
            p["q_num"] = p["q"].str.extract(r"(\d+)").astype(int)
            p["d_num"] = p["d"].str.extract(r"(\d+)").astype(int)
            p = p.sort_values(["q_num", "d_num", "t_num"])

            if view == "single":
                x_vals = p["t_num"].values
            else:
                ti = _time_index(p[["q_num", "d_num", "t_num", "q", "d"]].drop_duplicates()
                                  .rename(columns={}))
                # build a simple sequential index
                p["x"] = range(len(p))
                x_vals = p["x"].values

            price_fig.add_trace(go.Scatter(
                x=x_vals, y=p["value"].values,
                name=scenario, mode="lines",
                fill="tozeroy" if i == 0 else "none",
                fillcolor="rgba(44, 111, 173, 0.12)",
                line=dict(color=colors[i % len(colors)], width=1.5),
                hovertemplate=f"<b>{scenario}</b><br>%{{y:.1f}} USD/MWh<extra></extra>",
            ))

    price_fig.update_layout(
        margin=dict(l=10, r=20, t=10, b=30),
        xaxis_title="Hour(s)", yaxis_title="USD/MWh",
        plot_bgcolor="white", paper_bgcolor="white",
        hovermode="x unified",
    )
    return dispatch_fig, price_fig
