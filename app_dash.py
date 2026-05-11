from __future__ import annotations

import html as html_tools
import json
import math
import os
import tomllib
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

try:
    import comm

    _create_comm = comm.create_comm

    def _safe_create_comm(*args, **kwargs):
        try:
            return _create_comm(*args, **kwargs)
        except NotImplementedError as exc:
            raise ImportError("Dash Jupyter comms are unavailable outside Jupyter.") from exc

    comm.create_comm = _safe_create_comm
except ImportError:
    pass

from dash import Dash, Input, Output, dash_table, dcc, html


APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "Lost_Chicago.csv"
CHICAGO_CENTER = {"lat": 41.8781, "lng": -87.6298}


def clean_text(value: object, fallback: str = "Unknown") -> str:
    if pd.isna(value):
        return fallback
    text = str(value).strip()
    return text if text else fallback


def format_year(value: object) -> str:
    if pd.isna(value):
        return "Unknown"
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return clean_text(value)


def normalize_category(value: object, fallback: str = "Unknown") -> str:
    text = clean_text(value, fallback)
    normalized = " ".join(text.replace("/", " / ").split())
    replacements = {
        "Executive / Legislative Action": "Executive / Legislative Action",
        "Executive/Legislative Action": "Executive / Legislative Action",
        "Public housing policy": "Public Housing Policy",
        "Urban renewal": "Urban Renewal",
    }
    return replacements.get(normalized, normalized)


def load_lost_chicago() -> pd.DataFrame:
    data = pd.read_csv(DATA_PATH)
    data.columns = data.columns.str.strip()
    data = data.rename(
        columns={
            "year_built": "year built",
            "year_demolished": "year demolished",
        }
    )
    data["lat"] = pd.to_numeric(data["lat"], errors="coerce")
    data["lon"] = pd.to_numeric(data["lon"], errors="coerce")
    data["year built"] = pd.to_numeric(data["year built"], errors="coerce")
    data["year demolished"] = pd.to_numeric(data["year demolished"], errors="coerce")
    return data


def google_search_url(query: str) -> str:
    return f"https://www.google.com/search?{urlencode({'tbm': 'isch', 'q': query})}"


def google_maps_place_url(lat: float, lon: float, query: str) -> str:
    return (
        "https://www.google.com/maps/search/?"
        + urlencode({"api": "1", "query": f"{query} @{lat},{lon}"})
    )


def street_view_image_url(lat: float, lon: float, api_key: str) -> str:
    return (
        "https://maps.googleapis.com/maps/api/streetview?"
        + urlencode(
            {
                "size": "320x180",
                "location": f"{lat},{lon}",
                "fov": "80",
                "pitch": "0",
                "key": api_key,
            }
        )
    )


def image_html(src: str, alt: str, fallback_url: str = "") -> str:
    if not src:
        return ""
    safe_src = html_tools.escape(src, quote=True)
    safe_alt = html_tools.escape(alt, quote=True)
    if not fallback_url:
        return f'<img class="popup-image" src="{safe_src}" alt="{safe_alt}" loading="lazy" />'

    safe_fallback_url = html_tools.escape(fallback_url, quote=True)
    return (
        f'<img class="popup-image" src="{safe_src}" alt="{safe_alt}" loading="lazy" '
        "onerror=\"this.style.display='none';this.nextElementSibling.style.display='flex';\" />"
        f'<a class="image-fallback" href="{safe_fallback_url}" target="_blank" '
        'rel="noopener" style="display: none;">Find a historical photo on Google Images</a>'
    )


def image_fallback_html(fallback_url: str) -> str:
    safe_fallback_url = html_tools.escape(fallback_url, quote=True)
    return (
        f'<a class="image-fallback" href="{safe_fallback_url}" target="_blank" rel="noopener">'
        "Find a historical photo on Google Images</a>"
    )


def marker_payload(
    data: pd.DataFrame,
    popup_mode: str,
    api_key: str = "",
) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    duplicate_positions = data.groupby(["lat", "lon"]).cumcount()
    duplicate_counts = data.groupby(["lat", "lon"])["lat"].transform("size")

    for row_position, (_, row) in enumerate(data.iterrows()):
        name = clean_text(row.get("name"), "Lost Chicago site")
        replacement = clean_text(row.get("replacement"))
        source = clean_text(row.get("source"), "")
        source_html = ""
        if source:
            if source.startswith(("http://", "https://")):
                safe_source = html_tools.escape(source, quote=True)
                source_html = f'<a href="{safe_source}" target="_blank" rel="noopener">Source</a>'
            else:
                source_html = html_tools.escape(source)

        description = clean_text(row.get("Description/Comments"), "")
        lat = float(row["lat"])
        lon = float(row["lon"])
        display_lat = lat
        display_lon = lon
        duplicate_count = int(duplicate_counts.iloc[row_position])

        if duplicate_count > 1:
            angle = 2 * math.pi * int(duplicate_positions.iloc[row_position]) / duplicate_count
            offset = 0.00012
            display_lat += math.sin(angle) * offset
            display_lon += math.cos(angle) * offset

        if popup_mode == "Replacement":
            details = [
                ("Replacement", replacement),
                ("Category", clean_text(row.get("Replacement Categories"))),
                ("Former site", name),
                ("Neighborhood", clean_text(row.get("neighborhood"))),
                ("Former type", clean_text(row.get("type"))),
                ("Demolished", format_year(row.get("year demolished"))),
            ]
            street_view_src = street_view_image_url(lat, lon, api_key) if api_key else ""
            maps_url = google_maps_place_url(lat, lon, replacement)
            media_html = image_html(street_view_src, f"Google Street View near {replacement}")
            heading = name
            body = (
                f'<p class="mode-note">Replacement: {html_tools.escape(replacement)}. '
                "Current Google Street View near the replacement site.</p>"
                f'<footer><a href="{html_tools.escape(maps_url, quote=True)}" '
                'target="_blank" rel="noopener">Open replacement in Google Maps</a></footer>'
            )
        else:
            details = [
                ("Name", name),
                ("Neighborhood", clean_text(row.get("neighborhood"))),
                ("Type", clean_text(row.get("type"))),
                ("Built", format_year(row.get("year built"))),
                ("Demolished", format_year(row.get("year demolished"))),
                ("Cause", clean_text(row.get("cause"))),
                ("Replacement", replacement),
            ]
            old_photo_src = clean_text(row.get("img_link"), "")
            image_search_url = google_search_url(f"{name} Chicago historic building")
            media_html = image_html(
                old_photo_src,
                f"Historical image of {name}",
                image_search_url,
            )
            if not media_html:
                media_html = image_fallback_html(image_search_url)
            heading = name
            body = (
                f'{f"<p>{html_tools.escape(description)}</p>" if description else ""}'
                f'<footer><a href="{html_tools.escape(image_search_url, quote=True)}" '
                'target="_blank" rel="noopener">Search Google Images for historical photos</a>'
                f'{" · " + source_html if source_html else ""}</footer>'
            )

        detail_html = "".join(
            f"<dt>{html_tools.escape(label)}</dt><dd>{html_tools.escape(value)}</dd>"
            for label, value in details
            if value != "Unknown"
        )

        content = f"""
            <article class="info-window">
                {media_html}
                <p class="popup-kicker">{html_tools.escape(popup_mode)}</p>
                <h2>{html_tools.escape(heading)}</h2>
                <dl>{detail_html}</dl>
                {body}
            </article>
        """

        markers.append(
            {
                "title": name,
                "lat": lat,
                "lng": lon,
                "display_lat": display_lat,
                "display_lng": display_lon,
                "type": clean_text(row.get("type")),
                "content": content,
                "mode": popup_mode,
                "photo_query": f"{name} Chicago historic building",
                "photo_slot_id": "",
            }
        )

    return markers


def get_google_maps_api_key() -> str:
    local_secrets_path = APP_DIR / ".streamlit" / "secrets.toml"
    secret_key = ""
    if local_secrets_path.exists():
        with local_secrets_path.open("rb") as secrets_file:
            local_secrets = tomllib.load(secrets_file)
        secret_key = local_secrets.get("GOOGLE_MAPS_API_KEY", "")
    return str(secret_key or os.environ.get("GOOGLE_MAPS_API_KEY", "")).strip()


def google_maps_html(markers: list[dict[str, object]], api_key: str) -> str:
    markers_json = json.dumps(markers)
    center_json = json.dumps(CHICAGO_CENTER)
    safe_api_key = urlencode({"key": api_key}).replace("key=", "", 1)

    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body, #map {{
          height: 100%;
          margin: 0;
          width: 100%;
          font-family: Arial, sans-serif;
        }}

        .info-window {{
          max-width: 310px;
          color: #111827;
          line-height: 1.35;
        }}

        .info-window h2 {{
          font-size: 18px;
          margin: 0 0 10px;
        }}

        .popup-image {{
          border-radius: 6px;
          display: block;
          height: 180px;
          margin: 0 0 12px;
          object-fit: cover;
          width: 100%;
        }}

        .google-photo-slot:empty {{
          display: none;
        }}

        .image-fallback {{
          align-items: center;
          background: #f3f4f6;
          border: 1px solid #d1d5db;
          border-radius: 6px;
          box-sizing: border-box;
          color: #2563eb;
          display: flex;
          font-size: 13px;
          font-weight: 700;
          height: 96px;
          justify-content: center;
          margin: 0 0 12px;
          padding: 14px;
          text-align: center;
          text-decoration: none;
        }}

        .popup-kicker {{
          color: #6b7280;
          font-size: 11px;
          font-weight: 700;
          letter-spacing: 0;
          margin: 0 0 4px;
          text-transform: uppercase;
        }}

        .info-window dl {{
          display: grid;
          grid-template-columns: 92px 1fr;
          gap: 5px 10px;
          margin: 0 0 10px;
        }}

        .info-window dt {{
          color: #6b7280;
          font-size: 12px;
          font-weight: 700;
          text-transform: uppercase;
        }}

        .info-window dd {{
          margin: 0;
          font-size: 13px;
        }}

        .info-window p {{
          border-top: 1px solid #e5e7eb;
          margin: 10px 0 0;
          padding-top: 10px;
        }}

        .info-window .mode-note {{
          color: #4b5563;
          font-size: 13px;
        }}

        .info-window footer {{
          margin-top: 10px;
        }}

        .info-window a {{
          color: #2563eb;
          font-weight: 700;
          text-decoration: none;
        }}
      </style>
      <script>
        const LOST_CHICAGO_MARKERS = {markers_json};
        const CHICAGO_CENTER = {center_json};

        function initMap() {{
          const map = new google.maps.Map(document.getElementById("map"), {{
            center: CHICAGO_CENTER,
            zoom: 11,
            mapTypeControl: true,
            streetViewControl: true,
            fullscreenControl: true,
          }});

          const bounds = new google.maps.LatLngBounds();
          const infoWindow = new google.maps.InfoWindow();
          const placesService = new google.maps.places.PlacesService(map);

          function injectGooglePhoto(site) {{
            if (site.mode !== "Demolished" || !site.photo_slot_id || site.photoLoaded) {{
              return;
            }}

            site.photoLoaded = true;
            placesService.findPlaceFromQuery(
              {{
                query: site.photo_query,
                fields: ["name", "photos"],
              }},
              (results, status) => {{
                if (
                  status !== google.maps.places.PlacesServiceStatus.OK ||
                  !results ||
                  !results[0] ||
                  !results[0].photos ||
                  !results[0].photos[0]
                ) {{
                  return;
                }}

                const photoUrl = results[0].photos[0].getUrl({{
                  maxWidth: 320,
                  maxHeight: 180,
                }});
                const photoHtml =
                  `<img class="popup-image" src="${{photoUrl}}" alt="Google photo for ${{site.title}}" loading="lazy" />`;
                site.content = site.content.replace(
                  `<div class="google-photo-slot" id="${{site.photo_slot_id}}"></div>`,
                  photoHtml,
                );
                infoWindow.setContent(site.content);
              }},
            );
          }}

          LOST_CHICAGO_MARKERS.forEach((site) => {{
            const position = {{
              lat: site.display_lat ?? site.lat,
              lng: site.display_lng ?? site.lng,
            }};
            const marker = new google.maps.Marker({{
              position,
              map,
              title: site.title,
            }});

            marker.addListener("click", () => {{
              infoWindow.setContent(site.content);
              infoWindow.open(map, marker);
              injectGooglePhoto(site);
            }});

            bounds.extend(position);
          }});

          if (LOST_CHICAGO_MARKERS.length > 1) {{
            map.fitBounds(bounds, 42);
          }}
        }}

        window.initMap = initMap;
      </script>
      <script
        src="https://maps.googleapis.com/maps/api/js?key={safe_api_key}&libraries=places&callback=initMap&v=weekly"
        async
        defer
      ></script>
    </head>
    <body>
      <div id="map"></div>
    </body>
    </html>
    """


def structure_breakdown(data: pd.DataFrame) -> pd.DataFrame:
    breakdown = data.assign(
        structure_type=data["type"].map(normalize_category),
        loss_cause=data["cause"].map(normalize_category),
    )

    return (
        breakdown.groupby(["structure_type", "loss_cause"], dropna=False)
        .size()
        .reset_index(name="places")
        .sort_values(["places", "structure_type", "loss_cause"], ascending=[False, True, True])
    )


def cause_replacement_breakdown(data: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"cause", "Replacement Categories"}
    if data.empty or not required_columns.issubset(data.columns):
        return pd.DataFrame(
            columns=[
                "loss_cause",
                "cause_label",
                "replacement_category",
                "places",
                "total_places",
                "share_of_cause",
            ]
        )

    breakdown = data.assign(
        loss_cause=data["cause"].map(normalize_category),
        replacement_category=data["Replacement Categories"].map(normalize_category),
    )

    counts = (
        breakdown.groupby(["loss_cause", "replacement_category"], dropna=False)
        .size()
        .reset_index(name="places")
    )
    totals = counts.groupby("loss_cause", as_index=False)["places"].sum().rename(
        columns={"places": "total_places"}
    )

    counts = counts.merge(totals, on="loss_cause")
    counts["share_of_cause"] = counts["places"] / counts["total_places"] * 100
    counts["cause_label"] = counts.apply(
        lambda row: f"{row['loss_cause']} (n={row['total_places']})",
        axis=1,
    )

    return counts.sort_values(
        ["total_places", "loss_cause", "places", "replacement_category"],
        ascending=[False, True, False, True],
    )


def empty_figure(message: str):
    fig = px.scatter()
    fig.update_layout(
        annotations=[
            {
                "text": message,
                "showarrow": False,
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
            }
        ],
        height=520,
        margin=dict(t=20, r=10, b=10, l=10),
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def table_from_frame(data: pd.DataFrame, columns: list[str]) -> dash_table.DataTable:
    visible_columns = [column for column in columns if column in data.columns]
    return dash_table.DataTable(
        data=data[visible_columns].to_dict("records"),
        columns=[{"name": column, "id": column} for column in visible_columns],
        page_size=10,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={
            "fontFamily": "Arial, sans-serif",
            "fontSize": 13,
            "padding": "8px",
            "textAlign": "left",
            "maxWidth": 280,
            "whiteSpace": "normal",
        },
        style_header={"backgroundColor": "#f3f4f6", "fontWeight": "700"},
    )


DATA = load_lost_chicago()
GOOGLE_MAPS_API_KEY = get_google_maps_api_key()
TYPE_OPTIONS = [{"label": value, "value": value} for value in sorted(DATA["type"].dropna().unique())]
NEIGHBORHOOD_OPTIONS = [
    {"label": value, "value": value} for value in sorted(DATA["neighborhood"].dropna().unique())
]
MIN_YEAR = int(DATA["year demolished"].min())
MAX_YEAR = int(DATA["year demolished"].max())


app = Dash(__name__)
server = app.server
app.title = "Lost Chicago Map"

app.layout = html.Div(
    className="app-shell",
    children=[
        html.Aside(
            className="sidebar",
            children=[
                html.H1("Lost Chicago Places"),
                html.P("Demolished, transformed, or vanished Chicago places from Lost_Chicago3.csv."),
                html.Label("Pin information"),
                dcc.RadioItems(
                    id="popup-mode",
                    options=[
                        {"label": "Demolished", "value": "Demolished"},
                        {"label": "Replacement", "value": "Replacement"},
                    ],
                    value="Demolished",
                    inline=True,
                    className="choice-row",
                ),
                html.Label("Type"),
                dcc.Dropdown(
                    id="type-filter",
                    options=TYPE_OPTIONS,
                    value=[option["value"] for option in TYPE_OPTIONS],
                    multi=True,
                ),
                html.Label("Neighborhood"),
                dcc.Dropdown(
                    id="neighborhood-filter",
                    options=NEIGHBORHOOD_OPTIONS,
                    value=[option["value"] for option in NEIGHBORHOOD_OPTIONS],
                    multi=True,
                ),
                html.Label("Year demolished"),
                dcc.RangeSlider(
                    id="year-range",
                    min=MIN_YEAR,
                    max=MAX_YEAR,
                    value=[MIN_YEAR, MAX_YEAR],
                    marks={MIN_YEAR: str(MIN_YEAR), MAX_YEAR: str(MAX_YEAR)},
                    tooltip={"placement": "bottom", "always_visible": False},
                ),
                dcc.Checklist(
                    id="include-unknown-years",
                    options=[{"label": "Include unknown demolition years", "value": "include"}],
                    value=["include"],
                ),
            ],
        ),
        html.Main(
            className="main",
            children=[
                html.Div(id="metrics", className="metrics"),
                html.Section(id="map-container", className="map-section"),
                html.Section(
                    className="chart-grid",
                    children=[
                        html.Div(
                            className="chart-panel",
                            children=[
                                html.H2("Structure Type Breakdown"),
                                dcc.Graph(id="structure-chart", config={"displayModeBar": False}),
                                html.P(
                                    (
                                        "The middle ring groups places by structure type. "
                                        "The outer ring breaks each structure type into causes "
                                        "of loss; larger slices represent more places in the "
                                        "current filters. Hover over any slice to see its count "
                                        "and share."
                                    ),
                                    className="chart-note",
                                ),
                            ],
                        ),
                        html.Div(
                            className="chart-panel",
                            children=[
                                html.H2("Causes of Loss by Replacement Category"),
                                dcc.Graph(id="loss-chart", config={"displayModeBar": False}),
                                html.P(
                                    (
                                        "Each cell shows how many places share a cause of loss "
                                        "and replacement category. Darker cells indicate more "
                                        "places; hover for the count and share within that cause."
                                    ),
                                    className="chart-note",
                                ),
                            ],
                        ),
                    ],
                ),
                html.Details(
                    children=[
                        html.Summary("Mapped place data"),
                        html.Div(id="mapped-table"),
                    ]
                ),
                html.Details(
                    id="unmapped-details",
                    children=[
                        html.Summary("Rows missing coordinates"),
                        html.Div(id="unmapped-table"),
                    ],
                ),
            ],
        ),
    ],
)

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            body {
                margin: 0;
                background: #f9fafb;
                color: #111827;
                font-family: Arial, sans-serif;
            }

            .app-shell {
                display: grid;
                grid-template-columns: 320px minmax(0, 1fr);
                min-height: 100vh;
            }

            .sidebar {
                background: #ffffff;
                border-right: 1px solid #e5e7eb;
                box-sizing: border-box;
                padding: 24px;
                position: sticky;
                top: 0;
                height: 100vh;
                overflow-y: auto;
            }

            .sidebar h1 {
                font-size: 26px;
                margin: 0 0 8px;
            }

            .sidebar p {
                color: #4b5563;
                line-height: 1.4;
                margin: 0 0 22px;
            }

            .sidebar label {
                display: block;
                font-size: 13px;
                font-weight: 700;
                margin: 18px 0 8px;
            }

            .choice-row label,
            #include-unknown-years label {
                font-weight: 400;
                margin-right: 14px;
            }

            .main {
                box-sizing: border-box;
                padding: 24px;
            }

            .metrics {
                display: grid;
                gap: 12px;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                margin-bottom: 18px;
            }

            .metric {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 16px;
            }

            .metric-label {
                color: #6b7280;
                font-size: 12px;
                font-weight: 700;
                text-transform: uppercase;
            }

            .metric-value {
                font-size: 28px;
                font-weight: 700;
                margin-top: 6px;
            }

            .map-frame,
            .map-message {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                height: 700px;
                width: 100%;
            }

            .map-message {
                align-items: center;
                box-sizing: border-box;
                color: #4b5563;
                display: flex;
                font-weight: 700;
                justify-content: center;
                padding: 24px;
            }

            .chart-grid {
                display: grid;
                gap: 18px;
                grid-template-columns: minmax(0, 1fr);
                margin-top: 18px;
            }

            .chart-panel {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 14px;
            }

            .chart-panel h2 {
                font-size: 18px;
                margin: 0 0 10px;
            }

            .chart-note {
                color: #4b5563;
                font-size: 13px;
                line-height: 1.4;
                margin: 8px 0 0;
            }

            details {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                margin-top: 18px;
                padding: 14px;
            }

            summary {
                cursor: pointer;
                font-weight: 700;
                margin-bottom: 10px;
            }

            @media (max-width: 900px) {
                .app-shell {
                    display: block;
                }

                .sidebar {
                    height: auto;
                    position: static;
                }

                .metrics,
                .chart-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


def filtered_data(
    selected_types: list[str] | None,
    selected_neighborhoods: list[str] | None,
    year_range: list[int],
    include_unknown_years: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selected_types = selected_types or []
    selected_neighborhoods = selected_neighborhoods or []
    year_matches = DATA["year demolished"].between(year_range[0], year_range[1], inclusive="both")
    if "include" in include_unknown_years:
        year_matches = year_matches | DATA["year demolished"].isna()

    filtered = DATA[
        DATA["type"].isin(selected_types)
        & DATA["neighborhood"].isin(selected_neighborhoods)
        & year_matches
    ]
    mapped = filtered.dropna(subset=["lat", "lon"]).copy()
    unmapped = filtered[filtered[["lat", "lon"]].isna().any(axis=1)].copy()
    return filtered, mapped, unmapped


@app.callback(
    Output("metrics", "children"),
    Output("map-container", "children"),
    Output("structure-chart", "figure"),
    Output("loss-chart", "figure"),
    Output("mapped-table", "children"),
    Output("unmapped-table", "children"),
    Input("type-filter", "value"),
    Input("neighborhood-filter", "value"),
    Input("year-range", "value"),
    Input("include-unknown-years", "value"),
    Input("popup-mode", "value"),
)
def update_dashboard(
    selected_types,
    selected_neighborhoods,
    year_range,
    include_unknown_years,
    popup_mode,
):
    filtered, mapped, unmapped = filtered_data(
        selected_types,
        selected_neighborhoods,
        year_range,
        include_unknown_years,
    )

    metrics = [
        html.Div(
            className="metric",
            children=[
                html.Div(label, className="metric-label"),
                html.Div(f"{value:,}", className="metric-value"),
            ],
        )
        for label, value in [
            ("Filtered places", len(filtered)),
            ("Mapped pins", len(mapped)),
            ("Missing coordinates", len(unmapped)),
        ]
    ]

    if mapped.empty:
        map_panel = html.Div("No rows with coordinates match the current filters.", className="map-message")
    elif not GOOGLE_MAPS_API_KEY:
        map_panel = html.Div(
            'Add GOOGLE_MAPS_API_KEY to final_project/.streamlit/secrets.toml.',
            className="map-message",
        )
    else:
        map_panel = html.Iframe(
            srcDoc=google_maps_html(
                marker_payload(mapped, popup_mode, GOOGLE_MAPS_API_KEY),
                GOOGLE_MAPS_API_KEY,
            ),
            className="map-frame",
        )

    breakdown = structure_breakdown(filtered)
    if breakdown.empty:
        structure_fig = empty_figure("No structure types match the current filters.")
    else:
        structure_fig = px.sunburst(
            breakdown,
            path=[px.Constant("Lost Chicago"), "structure_type", "loss_cause"],
            values="places",
            color="structure_type",
            hover_data={"places": ":,", "structure_type": False, "loss_cause": False},
            labels={
                "structure_type": "Structure type",
                "loss_cause": "Cause",
                "places": "Lost places",
            },
        )
        structure_fig.update_traces(
            branchvalues="total",
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Lost places: %{value}<br>"
                "Share of parent: %{percentParent:.1%}<br>"
                "Share of total: %{percentRoot:.1%}<extra></extra>"
            ),
            insidetextorientation="radial",
            marker=dict(line=dict(color="#ffffff", width=4)),
        )
        structure_fig.update_layout(
            hoverlabel=dict(bgcolor="#111827", font_color="#ffffff", font_size=13),
            margin=dict(t=10, r=10, b=10, l=10),
            height=560,
            hovermode="closest",
            uniformtext=dict(minsize=11, mode="hide"),
        )

    loss_breakdown = cause_replacement_breakdown(filtered)
    if loss_breakdown.empty:
        loss_fig = empty_figure("No cause and replacement category records match the current filters.")
    else:
        cause_order = (
            loss_breakdown[["loss_cause", "total_places"]]
            .drop_duplicates()
            .sort_values(["total_places", "loss_cause"], ascending=[False, True])["loss_cause"]
            .tolist()
        )
        replacement_order = (
            loss_breakdown.groupby("replacement_category", as_index=False)["places"]
            .sum()
            .sort_values(["places", "replacement_category"], ascending=[False, True])[
                "replacement_category"
            ]
            .tolist()
        )
        count_matrix = (
            loss_breakdown.pivot_table(
                index="loss_cause",
                columns="replacement_category",
                values="places",
                fill_value=0,
                aggfunc="sum",
            )
            .reindex(index=cause_order, columns=replacement_order, fill_value=0)
            .astype(int)
        )
        share_matrix = count_matrix.div(count_matrix.sum(axis=1).replace(0, pd.NA), axis=0).fillna(0) * 100
        text_matrix = count_matrix.where(count_matrix > 0, "").astype(str)
        customdata = [
            [
                [int(count_matrix.iloc[row_index, col_index]), float(share_matrix.iloc[row_index, col_index])]
                for col_index in range(len(count_matrix.columns))
            ]
            for row_index in range(len(count_matrix.index))
        ]
        loss_fig = go.Figure(
            data=go.Heatmap(
                z=count_matrix.to_numpy(),
                x=count_matrix.columns.tolist(),
                y=count_matrix.index.tolist(),
                text=text_matrix.to_numpy(),
                texttemplate="%{text}",
                customdata=customdata,
                colorscale="YlGnBu",
                colorbar=dict(title="Places"),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Replacement category: %{x}<br>"
                    "Lost places: %{customdata[0]}<br>"
                    "Share of cause: %{customdata[1]:.1f}%<extra></extra>"
                ),
                xgap=2,
                ygap=2,
            )
        )
        loss_fig.update_layout(
            height=max(520, 58 * len(cause_order)),
            hoverlabel=dict(bgcolor="#111827", font_color="#ffffff", font_size=13),
            margin=dict(t=20, r=20, b=130, l=130),
            xaxis=dict(side="top", tickangle=35, title="Replacement category"),
            yaxis=dict(autorange="reversed", title="Cause of loss"),
        )

    table_columns = [
        "name",
        "neighborhood",
        "type",
        "year built",
        "year demolished",
        "lat",
        "lon",
        "cause",
        "replacement",
        "source",
        "Description/Comments",
        "Contributor",
    ]
    unmapped_columns = [
        "name",
        "neighborhood",
        "type",
        "year built",
        "year demolished",
        "cause",
        "replacement",
        "source",
        "Description/Comments",
        "Contributor",
    ]

    return (
        metrics,
        map_panel,
        structure_fig,
        loss_fig,
        table_from_frame(mapped, table_columns),
        table_from_frame(unmapped, unmapped_columns),
    )


if __name__ == "__main__":
    app.run(debug=True)
