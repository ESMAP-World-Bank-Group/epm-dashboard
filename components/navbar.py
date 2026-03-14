import dash_bootstrap_components as dbc
from dash import html, dcc
from data import loader

def _model_options():
    models = loader.get_available_models()
    return [
        {"label": f"{mt} / {reg}", "value": f"{mt}|{reg}"}
        for mt, reg in models
    ]

PAGES = [
    {"name": "Overview",          "path": "/"},
    {"name": "Evolution",         "path": "/evolution"},
    {"name": "Zonal Comparison",  "path": "/zonal-comparison"},
    {"name": "Dispatch",          "path": "/dispatch"},
    {"name": "Power Plants",      "path": "/power-plants"},
    {"name": "Results Table",     "path": "/results-table"},
]


def make_navbar():
    model_options = _model_options()
    default_model = model_options[0]["value"] if model_options else "regional|EAPP"

    nav_links = [
        dbc.NavItem(
            dbc.NavLink(p["name"], href=p["path"], active="exact",
                        className="nav-page-link")
        )
        for p in PAGES
    ]

    return dbc.Navbar(
        dbc.Container([
            # Brand
            html.A(
                dbc.Row([
                    dbc.Col(dbc.NavbarBrand("EPM Dashboard",
                                            className="ms-0 fw-bold",
                                            style={"letterSpacing": "0.5px"})),
                ], align="center", className="g-0"),
                href="/", style={"textDecoration": "none"},
            ),
            # Page links
            dbc.Nav(nav_links, navbar=True, className="mx-auto"),
            # Model / Region selector
            dbc.Row([
                dbc.Col(
                    dcc.Dropdown(
                        id="global-model-select",
                        options=model_options,
                        value=default_model,
                        clearable=False,
                        style={"minWidth": "160px", "fontSize": "0.85rem"},
                    ),
                    width="auto",
                ),
            ], align="center"),
        ], fluid=True),
        color="#1B2A4A",
        dark=True,
        sticky="top",
        className="navbar-main shadow-sm",
    )
