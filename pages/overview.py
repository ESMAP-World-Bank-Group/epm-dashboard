import math
import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State, callback, no_update
import plotly.graph_objects as go
import plotly.express as px
import plotly.colors as pc
import numpy as np
import pandas as pd
from data import loader

dash.register_page(__name__, path="/", name="Overview", order=0)

# ---------------------------------------------------------------------------
# Map helpers
# ---------------------------------------------------------------------------

def _arrowhead_geo(src_lat, src_lon, dst_lat, dst_lon, hw_deg=0.45):
    """Return (lats, lons) for a filled triangle arrowhead pointing src→dst."""
    cos_lat = math.cos(math.radians((src_lat + dst_lat) / 2))
    dlat = dst_lat - src_lat
    dlon = (dst_lon - src_lon) * cos_lat
    length = math.sqrt(dlat ** 2 + dlon ** 2)
    if length < 1e-6:
        return [], []
    ulat, ulon = dlat / length, dlon / length   # unit direction (cartesian)
    perp_lat, perp_lon = -ulon, ulat            # perpendicular (cartesian)
    tip_lat  = src_lat + 0.56 * (dst_lat - src_lat)
    tip_lon  = src_lon + 0.56 * (dst_lon - src_lon)
    base_lat = src_lat + 0.44 * (dst_lat - src_lat)
    base_lon = src_lon + 0.44 * (dst_lon - src_lon)
    c1_lat = base_lat + perp_lat * hw_deg
    c1_lon = base_lon + perp_lon * hw_deg / cos_lat
    c2_lat = base_lat - perp_lat * hw_deg
    c2_lon = base_lon - perp_lon * hw_deg / cos_lat
    return [tip_lat, c1_lat, c2_lat, tip_lat], [tip_lon, c1_lon, c2_lon, tip_lon]


# ---------------------------------------------------------------------------
# Dispatch chart helper
# ---------------------------------------------------------------------------

def _parse_time(df):
    for col, src in [("q_num", "q"), ("d_num", "d"), ("t_num", "t")]:
        df[col] = pd.to_numeric(df[src].astype(str).str.extract(r"(\d+)")[0], errors="coerce")
    df = df.dropna(subset=["q_num", "d_num", "t_num"])
    df[["q_num", "d_num", "t_num"]] = df[["q_num", "d_num", "t_num"]].astype(int)
    return df


def _dispatch_annual_fig(dispatch_df, zone, scenario, year, price_df=None, day_weights=None):
    """Annual stacked-area dispatch for one zone/scenario/year, with optional marginal cost."""
    df = dispatch_df[
        (dispatch_df["z"] == zone) &
        (dispatch_df["scenario"] == scenario) &
        (dispatch_df["y"] == year)
    ].copy()
    empty = go.Figure().update_layout(paper_bgcolor="white", plot_bgcolor="white",
                                      margin=dict(l=10, r=10, t=20, b=10))
    if df.empty:
        return empty

    df = _parse_time(df)
    slots = (df[["q_num", "d_num", "t_num", "q", "d"]].drop_duplicates()
               .sort_values(["q_num", "d_num", "t_num"])
               .reset_index(drop=True))
    slots["x"] = slots.index
    df = df.merge(slots, on=["q_num", "d_num", "t_num", "q", "d"], how="left")

    # Pre-compute y1 stacked extremes for zero-alignment of y2
    pos_sum = df[df["value"] > 0].groupby("x")["value"].sum()
    neg_sum = df[df["value"] < 0].groupby("x")["value"].sum()
    y1_max = pos_sum.max() if not pos_sum.empty else 1000
    y1_min = neg_sum.min() if not neg_sum.empty else 0

    fig = go.Figure()
    tech_list = [t for t in loader.TECH_ORDER if t in df["uni"].unique()]
    other = [t for t in df["uni"].unique() if t not in loader.TECH_ORDER and t != "Demand"]
    shown = set()
    for tech in other + tech_list:
        t_df = df[df["uni"] == tech].sort_values("x")
        if t_df.empty:
            continue
        xi, vals = t_df["x"].values, t_df["value"].values
        color = loader.TECH_COLORS.get(tech, "#aaaaaa")
        show = tech not in shown
        if show:
            shown.add(tech)
        pos, neg = np.maximum(vals, 0), np.minimum(vals, 0)
        if pos.sum() > 0:
            fig.add_trace(go.Scatter(
                x=xi, y=pos, name=tech, mode="none",
                fill="tonexty", stackgroup="pos",
                fillcolor=color, line=dict(width=0),
                showlegend=show, legendgroup=tech,
                hovertemplate=f"<b>{tech}</b>: %{{y:,.0f}} MW<extra></extra>",
            ))
        if neg.sum() < 0:
            fig.add_trace(go.Scatter(
                x=xi, y=neg, name=tech, mode="none",
                fill="tonexty", stackgroup="neg",
                fillcolor=color, line=dict(width=0),
                showlegend=False, legendgroup=tech,
                hovertemplate=f"<b>{tech}</b>: %{{y:,.0f}} MW<extra></extra>",
            ))

    dem = df[df["uni"] == "Demand"].sort_values("x")
    if not dem.empty:
        fig.add_trace(go.Scatter(
            x=dem["x"], y=dem["value"], name="Demand", mode="lines",
            line=dict(color="#e74c3c", width=1.5), showlegend=True,
        ))

    # Marginal cost on secondary y-axis
    has_price = False
    y2 = {}
    if price_df is not None and not price_df.empty:
        p = price_df[
            (price_df["z"] == zone) &
            (price_df["scenario"] == scenario) &
            (price_df["y"] == year)
        ].copy()
        if not p.empty:
            p = _parse_time(p)
            p = p.merge(slots[["q_num", "d_num", "t_num", "x"]], on=["q_num", "d_num", "t_num"], how="inner").sort_values("x")
            fig.add_trace(go.Scatter(
                x=p["x"], y=p["value"], name="Marginal Cost",
                mode="lines", yaxis="y2",
                line=dict(color="#2c3e50", width=1),
                hovertemplate="<b>Marginal Cost</b>: %{y:.1f} USD/MWh<extra></extra>",
                showlegend=True,
            ))
            has_price = True

            # Align y2 zero with y1 zero
            p_max_val = p["value"].max() * 1.1
            y1_span = y1_max - y1_min
            if y1_span > 0 and y1_min < 0:
                # Fraction of y1 range that lies below 0
                zero_frac = -y1_min / y1_span
                # Solve for y2_min so that 0 sits at the same fraction from the bottom
                y2_min = zero_frac * p_max_val / (zero_frac - 1)
            else:
                y2_min = 0
            y2 = dict(title="USD/MWh", overlaying="y", side="right",
                      showgrid=False, zeroline=False,
                      range=[y2_min, p_max_val])

    # Day separators (dotted) + quarter separators (solid) + % weight labels
    qd = (slots.groupby(["q_num", "d_num", "q", "d"])["x"]
          .agg(x_min="min", x_max="max").reset_index())
    first_q = qd["q_num"].min()
    n_total = len(qd)
    pct_default = 100.0 / n_total if n_total else 0

    for _, r in qd.iterrows():
        first_d_in_q = r["d_num"] == qd[qd["q_num"] == r["q_num"]]["d_num"].min()
        very_first   = (r["q_num"] == first_q and first_d_in_q)

        if not very_first:
            is_q = first_d_in_q
            fig.add_shape(type="line",
                          x0=r["x_min"] - 0.5, x1=r["x_min"] - 0.5,
                          y0=0, y1=1, xref="x", yref="paper",
                          line=dict(color="#bbbbbb" if is_q else "#e0e0e0",
                                    width=1.0 if is_q else 0.5,
                                    dash="solid" if is_q else "dot"))
        mid = (r["x_min"] + r["x_max"]) / 2
        pct = day_weights.get((r["q"], r["d"]), pct_default) if day_weights else pct_default
        fig.add_annotation(x=mid, y=1.005, xref="x", yref="paper",
                           text=f"<span style='font-size:7px;color:#cccccc'>{pct:.1f}%</span>",
                           showarrow=False, xanchor="center", yanchor="bottom")

    # Quarter labels below x-axis
    for q_num in sorted(qd["q_num"].unique()):
        qr = qd[qd["q_num"] == q_num]
        mid = (qr["x_min"].min() + qr["x_max"].max()) / 2
        fig.add_annotation(x=mid, y=1.03, xref="x", yref="paper",
                           text=f"<span style='font-size:8px;color:#888'>Q{int(q_num)}</span>",
                           showarrow=False, xanchor="center", yanchor="bottom")

    fig.update_layout(
        margin=dict(l=10, r=50 if has_price else 10, t=25, b=10),
        paper_bgcolor="white", plot_bgcolor="white",
        legend=dict(orientation="v", x=1.08 if has_price else 1.01, y=1, font=dict(size=9)),
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(title="MW", zeroline=True, zerolinecolor="#cccccc",
                   range=[y1_min * 1.05 if y1_min < 0 else None, y1_max * 1.05]),
        yaxis2=y2,
        font=dict(size=10),
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def kpi_card(title, value_id, icon, color, sub_id=None, sub_label=None):
    value_col = [
        html.P(title, className="text-muted mb-0", style={"fontSize": "0.78rem", "fontWeight": 600}),
        html.H4(id=value_id, className="mb-0 fw-bold"),
    ]
    if sub_id:
        value_col.append(
            html.P([html.Span(sub_label + " ", style={"fontWeight": 500}),
                    html.Span(id=sub_id)],
                   className="text-muted mb-0", style={"fontSize": "0.78rem"})
        )
    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col(html.I(className=f"bi {icon}", style={"fontSize": "2rem", "color": color}), width=3),
                dbc.Col(value_col, width=9),
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
        dbc.Col(kpi_card("Generation Capacity",    "ov-kpi-gen-capa",      "bi-lightning-charge",  "#2d9e4f"), md=3),
        dbc.Col(kpi_card("Total Demand",           "ov-kpi-demand-energy", "bi-graph-up",          "#f77f00",
                         sub_id="ov-kpi-demand-peak", sub_label="Peak:"), md=3),
        dbc.Col(kpi_card("Transmission Capacity",  "ov-kpi-tr-capa",       "bi-diagram-3",         "#2c6fad"), md=3),
        dbc.Col(kpi_card("Trade Volume",           "ov-kpi-trade",         "bi-arrow-left-right",  "#7b4f9e"), md=3),
    ], className="mb-3 g-3"),

    # ── Map (left) + Capacity & Price stacked (right) ────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("Interconnections — Net Flow & Utilization")),
            dbc.CardBody(dcc.Graph(id="ov-map", config={"displayModeBar": False},
                                   style={"height": "400px"}),
                         style={"padding": "4px"}),
        ], className="shadow-sm h-100"), md=6),
        dbc.Col(dbc.Card([
            dbc.CardHeader(html.B("Capacity Mix — Selected Year")),
            dbc.CardBody(dcc.Graph(id="ov-capacity-bar", config={"displayModeBar": False},
                                   style={"height": "390px"})),
        ], className="shadow-sm h-100"), md=6),
    ], className="mb-3 g-3"),

    # ── Country dispatch ──────────────────────────────────────────────────
    dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardHeader(dbc.Row([
                dbc.Col(html.B("Annual Dispatch"), width="auto"),
                dbc.Col(
                    dcc.Dropdown(id="ov-dispatch-zone", placeholder="Select a zone…",
                                 clearable=True,
                                 style={"fontSize": "0.82rem", "minWidth": "160px"}),
                    width="auto",
                ),
            ], align="center", className="g-2")),
            dbc.CardBody(dcc.Graph(id="ov-dispatch", config={"displayModeBar": False},
                                   style={"height": "380px"})),
        ], className="shadow-sm"), md=12),
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
    State("ov-scenario",  "value"),
    State("ov-year",      "value"),
)
def init_filters(store, cur_scenario, cur_year):
    mt, reg = store["model_type"], store["region"]
    scenarios = loader.get_scenarios(mt, reg)
    years     = loader.get_years(mt, reg)
    s_opts = [{"label": s, "value": s} for s in scenarios]
    y_opts = [{"label": str(int(y)), "value": y} for y in years]
    default_s = "baseline" if "baseline" in scenarios else (scenarios[0] if scenarios else None)
    s_val = cur_scenario if cur_scenario in scenarios else default_s
    y_val = cur_year     if cur_year     in years     else (years[-1]    if years     else None)
    s_out = s_val if s_val != cur_scenario else no_update
    y_out = y_val if y_val != cur_year     else no_update
    return s_opts, s_out, y_opts, y_out


@callback(
    Output("ov-kpi-gen-capa",      "children"),
    Output("ov-kpi-demand-energy", "children"),
    Output("ov-kpi-demand-peak",   "children"),
    Output("ov-kpi-tr-capa",       "children"),
    Output("ov-kpi-trade",         "children"),
    Input("ov-scenario", "value"),
    Input("ov-year",     "value"),
    Input("global-store", "data"),
)
def update_kpis(scenario, year, store):
    if not scenario or not year:
        return "—", "—", "—", "—", "—"
    mt, reg = store["model_type"], store["region"]

    # Generation capacity (GW) for selected year
    tf = loader.load_techfuel(mt, reg)
    gen_capa_val = "—"
    if not tf.empty:
        sub = tf[(tf["scenario"] == scenario) &
                 (tf["attribute"] == "CapacityTechFuel") &
                 (tf["y"] == year)]
        if not sub.empty:
            total_mw = sub["value"].sum()
            gen_capa_val = f"{total_mw/1000:.1f} GW"

    # Demand energy (TWh) and peak (GW) for selected year
    yz = loader.load_yearly_zone(mt, reg)
    demand_energy_val, demand_peak_val = "—", "—"
    if not yz.empty:
        sub_y = yz[(yz["scenario"] == scenario) & (yz["y"] == year)]
        dem_e = sub_y[sub_y["attribute"] == "DemandEnergyZone"]["value"].sum()
        dem_p = sub_y[sub_y["attribute"] == "DemandPeakZone"]["value"].sum()
        demand_energy_val = f"{dem_e/1000:.1f} TWh" if dem_e > 0 else "—"
        demand_peak_val   = f"{dem_p/1000:.1f} GW"  if dem_p > 0 else "—"

    # Transmission capacity (MW): sum unique corridors (take max of each direction pair)
    tr = loader.load_transmission(mt, reg)
    tr_capa_val = "—"
    if not tr.empty:
        sub_tr = tr[(tr["scenario"] == scenario) &
                    (tr["attribute"] == "TransmissionCapacity") &
                    (tr["y"] == year)].dropna(subset=["value", "z2"])
        if not sub_tr.empty:
            sub_tr["key"] = sub_tr.apply(lambda r: tuple(sorted([r["z"], r["z2"]])), axis=1)
            total_cap = sub_tr.groupby("key")["value"].max().sum()
            tr_capa_val = f"{total_cap:,.0f} MW"

    # Trade volume (GWh): sum all Interchange values ÷ 2 (each flow counted twice)
    trade_val = "—"
    if not tr.empty:
        sub_ic = tr[(tr["scenario"] == scenario) &
                    (tr["attribute"] == "Interchange") &
                    (tr["y"] == year)].dropna(subset=["value"])
        if not sub_ic.empty:
            total_trade = sub_ic["value"].sum() / 2
            trade_val = f"{total_trade:,.0f} GWh"

    return gen_capa_val, demand_energy_val, demand_peak_val, tr_capa_val, trade_val


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
    zone_coords = loader.load_zone_coords(mt, reg)
    tf = loader.load_techfuel(mt, reg)
    if tf.empty:
        return empty_fig, empty_fig

    sub = tf[(tf["scenario"] == scenario) &
             (tf["attribute"] == "CapacityTechFuel") &
             (tf["y"] == year)]

    # ── Interconnection map ───────────────────────────────────────────────
    tr = loader.load_transmission(mt, reg)
    map_fig = go.Figure()

    if not tr.empty:
        tr_y = tr[(tr["scenario"] == scenario) & (tr["y"] == year)]

        def _get(attr, z1, z2):
            v = tr_y[(tr_y["attribute"] == attr) & (tr_y["z"] == z1) & (tr_y["z2"] == z2)]["value"]
            return float(v.iloc[0]) if not v.empty else 0.0

        # Canonical corridor pairs present in data
        pairs_raw = tr_y[tr_y["attribute"] == "Interchange"][["z", "z2"]].drop_duplicates()
        seen = set()
        corridors = []
        for _, row in pairs_raw.iterrows():
            z1, z2 = row["z"], row["z2"]
            if z1 not in zone_coords or z2 not in zone_coords:
                continue
            key = tuple(sorted([z1, z2]))
            if key in seen:
                continue
            seen.add(key)
            corridors.append(key)

        if corridors:
            # Compute max interchange for width scaling
            vols = []
            for z1, z2 in corridors:
                v = abs(_get("Interchange", z1, z2)) + abs(_get("Interchange", z2, z1))
                vols.append(v)
            max_vol = max(vols) if vols else 1.0

            for (z1, z2), vol in zip(corridors, vols):
                lat1, lon1 = zone_coords[z1]
                lat2, lon2 = zone_coords[z2]

                # Utilization: average of both directions
                u1 = _get("InterconUtilization", z1, z2)
                u2 = _get("InterconUtilization", z2, z1)
                util = (u1 + u2) / 2 if (u1 + u2) > 0 else max(u1, u2)

                # Capacity
                cap = max(_get("TransmissionCapacity", z1, z2),
                          _get("TransmissionCapacity", z2, z1))

                # Net direction: compare interchange in each direction
                flow_fwd = abs(_get("Interchange", z1, z2))
                flow_bwd = abs(_get("Interchange", z2, z1))
                if flow_fwd >= flow_bwd:
                    src_lat, src_lon = lat1, lon1
                    dst_lat, dst_lon = lat2, lon2
                    src_z, dst_z = z1, z2
                else:
                    src_lat, src_lon = lat2, lon2
                    dst_lat, dst_lon = lat1, lon1
                    src_z, dst_z = z2, z1

                color = pc.sample_colorscale("YlOrRd", [min(max(util, 0), 1)])[0]
                width = 1.5 + 5.0 * (vol / max_vol)

                hover = (f"<b>{z1} ↔ {z2}</b><br>"
                         f"Net flow: {src_z} → {dst_z}<br>"
                         f"Volume: {vol:,.0f} GWh<br>"
                         f"Capacity: {cap:,.0f} MW<br>"
                         f"Utilization: {util*100:.1f}%"
                         "<extra></extra>")

                # Corridor line — interpolate points so hover fires along full length
                n = 20
                lats_line = [lat1 + i / n * (lat2 - lat1) for i in range(n + 1)]
                lons_line = [lon1 + i / n * (lon2 - lon1) for i in range(n + 1)]
                map_fig.add_trace(go.Scattergeo(
                    lat=lats_line, lon=lons_line,
                    mode="lines",
                    line=dict(color=color, width=width),
                    hovertemplate=hover,
                    showlegend=False,
                ))

                # Filled arrowhead triangle (no hover — purely visual)
                arr_lats, arr_lons = _arrowhead_geo(
                    src_lat, src_lon, dst_lat, dst_lon, hw_deg=0.45)
                if arr_lats:
                    map_fig.add_trace(go.Scattergeo(
                        lat=arr_lats, lon=arr_lons,
                        mode="lines",
                        fill="toself",
                        fillcolor=color,
                        line=dict(color=color, width=0.5),
                        hoverinfo="skip",
                        showlegend=False,
                    ))

    # ── Per-zone metrics for dot hover ───────────────────────────────────
    yz = loader.load_yearly_zone(mt, reg)
    yz_y = yz[(yz["scenario"] == scenario) & (yz["y"] == year)] if not yz.empty else pd.DataFrame()
    tr_ic = (tr[(tr["scenario"] == scenario) & (tr["y"] == year) &
                (tr["attribute"] == "Interchange")].dropna(subset=["value", "z2"])
             if not tr.empty else pd.DataFrame())

    def _zone_val(df, attr, zone_col="z"):
        if df.empty:
            return {}
        sub = df[df["attribute"] == attr] if "attribute" in df.columns else df
        return sub.groupby(zone_col)["value"].sum().to_dict()

    capa_by_z  = _zone_val(
        tf[(tf["scenario"] == scenario) & (tf["attribute"] == "CapacityTechFuel") & (tf["y"] == year)],
        "CapacityTechFuel") if not tf.empty else {}
    gen_by_z   = _zone_val(
        tf[(tf["scenario"] == scenario) & (tf["attribute"] == "EnergyTechFuelComplete") & (tf["y"] == year)],
        "EnergyTechFuelComplete") if not tf.empty else {}
    demand_by_z = _zone_val(yz_y[yz_y["attribute"] == "DemandEnergyZone"],  "DemandEnergyZone")
    price_by_z  = yz_y[yz_y["attribute"] == "GenCostsPerMWh"].groupby("z")["value"].mean().to_dict() \
                  if not yz_y.empty else {}
    exports_by_z = tr_ic.groupby("z")["value"].sum().to_dict()  if not tr_ic.empty else {}
    imports_by_z = tr_ic.groupby("z2")["value"].sum().to_dict() if not tr_ic.empty else {}

    # Zone dots + labels
    z_in_data = set(tr[(tr["scenario"] == scenario)]["z"].dropna().unique()) | \
                set(tr[(tr["scenario"] == scenario)]["z2"].dropna().unique()) \
                if not tr.empty else set()
    zone_lats, zone_lons, zone_names, zone_hovers = [], [], [], []
    for z, (lat, lon) in zone_coords.items():
        if z not in z_in_data:
            continue
        capa  = capa_by_z.get(z, 0)
        gen   = gen_by_z.get(z, 0)
        dem   = demand_by_z.get(z, 0)
        exp_  = exports_by_z.get(z, 0)
        imp_  = imports_by_z.get(z, 0)
        price = price_by_z.get(z, 0)
        zone_lats.append(lat)
        zone_lons.append(lon)
        zone_names.append(z)
        zone_hovers.append(
            f"<b>{z}</b><br>"
            f"Capacity: {capa/1000:.1f} GW<br>"
            f"Demand: {dem/1000:.1f} TWh<br>"
            f"Generation: {gen/1000:.1f} TWh<br>"
            f"Exports: {exp_:,.0f} GWh<br>"
            f"Imports: {imp_:,.0f} GWh<br>"
            f"Price: {price:.1f} USD/MWh"
            "<extra></extra>"
        )

    if zone_lats:
        prices_list = [price_by_z.get(z, 0) for z in zone_names]
        p_min = min(prices_list) if prices_list else 0
        p_max = max(prices_list) if prices_list else 1
        map_fig.add_trace(go.Scattergeo(
            lat=zone_lats, lon=zone_lons,
            mode="markers+text",
            text=zone_names,
            textposition="top right",
            textfont=dict(size=9, color="#555555"),
            marker=dict(
                size=10,
                color=prices_list,
                colorscale="Blues",
                cmin=p_min, cmax=p_max,
                showscale=True,
                colorbar=dict(
                    title=dict(text="Price<br>($/MWh)", side="right"),
                    thickness=12, len=0.40,
                    x=0.01, xanchor="left",
                    y=0.15, yanchor="bottom",
                    tickfont=dict(size=8),
                ),
                line=dict(color="white", width=1),
            ),
            hovertemplate=zone_hovers,
            showlegend=False,
        ))

    # Invisible colorbar trace for utilization scale
    map_fig.add_trace(go.Scattergeo(
        lat=[None], lon=[None], mode="markers",
        marker=dict(
            colorscale="YlOrRd", cmin=0, cmax=100,
            color=[50], showscale=True,
            colorbar=dict(
                title=dict(text="Utilization (%)", side="right"),
                thickness=12, len=0.55, x=1.0,
                tickvals=[0, 25, 50, 75, 100],
                ticktext=["0%", "25%", "50%", "75%", "100%"],
            ),
        ),
        showlegend=False, hoverinfo="skip",
    ))

    if zone_coords:
        all_lats = [lat for lat, lon in zone_coords.values()]
        all_lons = [lon for lat, lon in zone_coords.values()]
        lat_pad = max(3, (max(all_lats) - min(all_lats)) * 0.15)
        lon_pad = max(3, (max(all_lons) - min(all_lons)) * 0.15)
        lat_range = [min(all_lats) - lat_pad, max(all_lats) + lat_pad]
        lon_range = [min(all_lons) - lon_pad, max(all_lons) + lon_pad]
    else:
        lat_range, lon_range = [-12, 34], [10, 52]

    map_fig.update_geos(
        scope="africa",
        showcoastlines=True, coastlinecolor="#cccccc",
        showcountries=True, countrycolor="#dddddd",
        showland=True, landcolor="#f5f5f5",
        showframe=False, projection_type="mercator",
        lataxis_range=lat_range,
        lonaxis_range=lon_range,
    )
    map_fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="white", geo_bgcolor="#e8f4fd",
    )

    # ── Capacity stacked bar ─────────────────────────────────────────────
    tech_order = [t for t in loader.TECH_ORDER if t in sub["techfuel"].unique()]
    other = [t for t in sub["techfuel"].unique() if t not in tech_order]
    tech_order = other + tech_order

    pivot = sub.groupby(["z", "techfuel"])["value"].sum().reset_index()
    zone_order = (pivot.groupby("z")["value"].sum()
                  .sort_values(ascending=False).index.tolist())
    bar_fig = px.bar(
        pivot, x="z", y="value", color="techfuel",
        color_discrete_map=loader.TECH_COLORS,
        category_orders={"techfuel": tech_order, "z": zone_order},
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
    Output("ov-dispatch-zone", "options"),
    Input("global-store", "data"),
)
def update_dispatch_zone_opts(store):
    mt, reg = store["model_type"], store["region"]
    zones = loader.get_zones(mt, reg)
    return [{"label": z, "value": z} for z in zones]


@callback(
    Output("ov-dispatch", "figure"),
    Input("ov-dispatch-zone", "value"),
    State("ov-scenario",      "value"),
    State("ov-year",          "value"),
    State("global-store",     "data"),
)
def update_country_dispatch(zone, scenario, year, store):
    empty = go.Figure().update_layout(paper_bgcolor="white", plot_bgcolor="white",
                                      margin=dict(l=10, r=10, t=10, b=10))
    if not zone or not scenario or not year:
        return empty

    mt, reg = store["model_type"], store["region"]
    dispatch_df = loader.load_dispatch(mt, reg)
    if dispatch_df.empty:
        return empty

    price_df   = loader.load_hourly_price(mt, reg)
    day_weights = loader.load_phours(mt, reg)
    return _dispatch_annual_fig(dispatch_df, zone, scenario, year,
                                price_df=price_df if not price_df.empty else None,
                                day_weights=day_weights if day_weights else None)
