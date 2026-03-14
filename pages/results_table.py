import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, callback, dash_table
import pandas as pd
from data import loader

dash.register_page(__name__, path="/results-table", name="Results Table", order=5)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dbc.Container([
    # ── Filter strip ─────────────────────────────────────────────────────
    dbc.Card(dbc.CardBody(dbc.Row([
        dbc.Col([
            html.Label("Scenario", className="form-label-sm"),
            dcc.Dropdown(id="rt-scenario", multi=True, placeholder="All",
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Country", className="form-label-sm"),
            dcc.Dropdown(id="rt-country", multi=True, placeholder="All",
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Zone", className="form-label-sm"),
            dcc.Dropdown(id="rt-zone", multi=True, placeholder="All",
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            html.Label("Attribute", className="form-label-sm"),
            dcc.Dropdown(id="rt-attribute", multi=True, placeholder="All",
                         style={"fontSize": "0.85rem"}),
        ], md=3),
        dbc.Col([
            html.Label("Year", className="form-label-sm"),
            dcc.Dropdown(id="rt-year", multi=True, placeholder="All",
                         style={"fontSize": "0.85rem"}),
        ], md=2),
        dbc.Col([
            dbc.Button("Export CSV", id="rt-export-btn", color="secondary",
                       size="sm", className="mt-3"),
            dcc.Download(id="rt-download"),
        ], md=1),
    ], className="g-2")), className="mb-3 shadow-sm filter-card"),

    # ── Row count ─────────────────────────────────────────────────────────
    html.Div(id="rt-row-count", className="text-muted mb-2",
             style={"fontSize": "0.82rem"}),

    # ── Data table ────────────────────────────────────────────────────────
    dbc.Card([
        dbc.CardBody(
            dash_table.DataTable(
                id="rt-table",
                columns=[],
                data=[],
                page_size=25,
                page_action="native",
                sort_action="native",
                filter_action="native",
                style_table={"overflowX": "auto"},
                style_header={
                    "backgroundColor": "#1B2A4A",
                    "color": "white",
                    "fontWeight": "bold",
                    "fontSize": "12px",
                    "border": "1px solid #dee2e6",
                },
                style_cell={
                    "fontSize": "11px",
                    "padding": "6px 10px",
                    "border": "1px solid #dee2e6",
                    "textAlign": "left",
                    "minWidth": "60px",
                    "maxWidth": "220px",
                    "overflow": "hidden",
                    "textOverflow": "ellipsis",
                },
                style_data_conditional=[
                    {"if": {"row_index": "odd"},
                     "backgroundColor": "#f8f9fa"},
                    {"if": {"filter_query": "{value} > 0",
                            "column_id": "value"},
                     "color": "#155724"},
                    {"if": {"filter_query": "{value} < 0",
                            "column_id": "value"},
                     "color": "#721c24"},
                ],
                tooltip_delay=0,
                tooltip_duration=None,
            )
        ),
    ], className="shadow-sm"),
], fluid=True, className="py-3 px-4")


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

@callback(
    Output("rt-scenario",  "options"),
    Output("rt-country",   "options"),
    Output("rt-zone",      "options"),
    Output("rt-attribute", "options"),
    Output("rt-year",      "options"),
    Input("global-store",  "data"),
)
def init_rt_filters(store):
    mt, reg = store["model_type"], store["region"]

    scenarios  = loader.get_scenarios(mt, reg)
    countries  = loader.get_countries(mt, reg)
    zones      = loader.get_zones(mt, reg)
    years      = loader.get_years(mt, reg)

    # Load summary to get all attributes across all files
    tf = loader.load_techfuel(mt, reg)
    costs = loader.load_costs(mt, reg)
    capex = loader.load_capex(mt, reg)
    yz    = loader.load_yearly_zone(mt, reg)

    attrs = set()
    for df in [tf, costs, capex, yz]:
        if not df.empty and "attribute" in df.columns:
            attrs.update(df["attribute"].dropna().unique().tolist())

    s_opts  = [{"label": s, "value": s} for s in sorted(scenarios)]
    c_opts  = [{"label": c, "value": c} for c in sorted(countries)]
    z_opts  = [{"label": z, "value": z} for z in sorted(zones)]
    a_opts  = [{"label": a, "value": a} for a in sorted(attrs)]
    y_opts  = [{"label": str(int(y)), "value": y} for y in sorted(years)]
    return s_opts, c_opts, z_opts, a_opts, y_opts


@callback(
    Output("rt-table",     "columns"),
    Output("rt-table",     "data"),
    Output("rt-row-count", "children"),
    Input("rt-scenario",   "value"),
    Input("rt-country",    "value"),
    Input("rt-zone",       "value"),
    Input("rt-attribute",  "value"),
    Input("rt-year",       "value"),
    Input("global-store",  "data"),
)
def update_table(scenarios, countries, zones, attributes, years, store):
    mt, reg = store["model_type"], store["region"]

    dfs = []
    for df, name in [
        (loader.load_techfuel(mt, reg),    "Capacity / Generation"),
        (loader.load_costs(mt, reg),       "Costs"),
        (loader.load_capex(mt, reg),       "CAPEX"),
        (loader.load_yearly_zone(mt, reg), "Yearly Zone"),
    ]:
        if not df.empty:
            dfs.append(df)

    if not dfs:
        return [], [], "No data."

    df_all = pd.concat(dfs, ignore_index=True)

    # Apply filters
    if scenarios:
        df_all = df_all[df_all["scenario"].isin(scenarios)]
    if countries and "c" in df_all.columns:
        df_all = df_all[df_all["c"].isin(countries)]
    if zones and "z" in df_all.columns:
        df_all = df_all[df_all["z"].isin(zones)]
    if attributes:
        df_all = df_all[df_all["attribute"].isin(attributes)]
    if years:
        df_all = df_all[df_all["y"].isin(years)]

    # Round value
    if "value" in df_all.columns:
        df_all["value"] = pd.to_numeric(df_all["value"], errors="coerce").round(4)

    # Select useful columns and drop duplicates
    keep = [c for c in ["scenario", "c", "z", "attribute", "y", "techfuel", "uni", "tech", "f", "g", "value"]
            if c in df_all.columns]
    df_out = df_all[keep].drop_duplicates().reset_index(drop=True)

    # Cap display rows
    MAX_ROWS = 5000
    if len(df_out) > MAX_ROWS:
        df_out = df_out.head(MAX_ROWS)
        count_msg = f"Showing first {MAX_ROWS:,} rows (apply filters to narrow down)"
    else:
        count_msg = f"{len(df_out):,} rows"

    columns = [{"name": c.upper(), "id": c, "type": "numeric" if c == "value" else "text"}
               for c in df_out.columns]
    data = df_out.to_dict("records")
    return columns, data, count_msg


@callback(
    Output("rt-download", "data"),
    Input("rt-export-btn", "n_clicks"),
    Input("rt-table", "data"),
    Input("rt-table", "columns"),
    prevent_initial_call=True,
)
def export_csv(n_clicks, data, columns):
    from dash import ctx
    if ctx.triggered_id != "rt-export-btn" or not data:
        return dash.no_update
    col_names = [c["id"] for c in columns]
    df = pd.DataFrame(data, columns=col_names)
    return dcc.send_data_frame(df.to_csv, "epm_results_export.csv", index=False)
