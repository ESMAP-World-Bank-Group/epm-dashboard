import dash
import dash_bootstrap_components as dbc
from dash import html, dcc, Input, Output, State
from components.navbar import make_navbar
from data import loader

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.FLATLY, dbc.icons.BOOTSTRAP],
    suppress_callback_exceptions=True,
    title="EPM Dashboard",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)
server = app.server

app.layout = html.Div([
    # Global store: model type + region, shared across all pages
    dcc.Store(
        id="global-store",
        storage_type="session",
        data={"model_type": "regional", "region": "EAPP"},
    ),
    # Refresh model list every 10 seconds (picks up newly added folders)
    dcc.Interval(id="model-refresh-interval", interval=10_000, n_intervals=0),
    make_navbar(),
    html.Div(
        dash.page_container,
        style={"minHeight": "calc(100vh - 58px)", "backgroundColor": "#F0F2F5"},
    ),
])


@app.callback(
    Output("global-store", "data"),
    Input("global-model-select", "value"),
)
def update_global_store(model_value):
    if not model_value:
        return {"model_type": "regional", "region": "EAPP"}
    parts = model_value.split("|", 1)
    return {"model_type": parts[0], "region": parts[1]}


@app.callback(
    Output("global-model-select", "options"),
    Output("global-model-select", "value"),
    Input("model-refresh-interval", "n_intervals"),
    State("global-model-select", "value"),
)
def refresh_model_list(_, current_value):
    models = loader.get_available_models()
    options = [{"label": f"{mt} / {reg}", "value": f"{mt}|{reg}"} for mt, reg in models]
    # Keep the current selection if it still exists, else prefer EAPP, else first
    valid = current_value and any(o["value"] == current_value for o in options)
    if valid:
        value = current_value
    elif any(o["value"] == "regional|EAPP" for o in options):
        value = "regional|EAPP"
    else:
        value = options[0]["value"] if options else None
    return options, value


if __name__ == "__main__":
    app.run(debug=True)
