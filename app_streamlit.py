from __future__ import annotations

import html
import json
import math
import os
import tomllib
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components


APP_DIR = Path(__file__).parent
DATA_PATH = APP_DIR / "Lost_Chicago.csv"
CHICAGO_CENTER = {"lat": 41.8781, "lng": -87.6298}


st.set_page_config(
    page_title="Lost Chicago Map",
    page_icon="map",
    layout="wide",
)


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


@st.cache_data
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
    safe_src = html.escape(src, quote=True)
    safe_alt = html.escape(alt, quote=True)
    if not fallback_url:
        return f'<img class="popup-image" src="{safe_src}" alt="{safe_alt}" loading="lazy" />'

    safe_fallback_url = html.escape(fallback_url, quote=True)
    return (
        f'<img class="popup-image" src="{safe_src}" alt="{safe_alt}" loading="lazy" '
        "onerror=\"this.style.display='none';this.nextElementSibling.style.display='flex';\" />"
        f'<a class="image-fallback" href="{safe_fallback_url}" target="_blank" '
        'rel="noopener" style="display: none;">Find a historical photo on Google Images</a>'
    )


def image_fallback_html(fallback_url: str) -> str:
    safe_fallback_url = html.escape(fallback_url, quote=True)
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
                safe_source = html.escape(source, quote=True)
                source_html = f'<a href="{safe_source}" target="_blank" rel="noopener">Source</a>'
            else:
                source_html = html.escape(source)

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
                f'<p class="mode-note">Replacement: {html.escape(replacement)}. '
                "Current Google Street View near the replacement site.</p>"
                f'<footer><a href="{html.escape(maps_url, quote=True)}" target="_blank" rel="noopener">'
                "Open replacement in Google Maps</a></footer>"
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
                f'{f"<p>{html.escape(description)}</p>" if description else ""}'
                f'<footer><a href="{html.escape(image_search_url, quote=True)}" target="_blank" rel="noopener">'
                "Search Google Images for historical photos</a>"
                f'{" · " + source_html if source_html else ""}</footer>'
            )

        detail_html = "".join(
            f"<dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd>"
            for label, value in details
            if value != "Unknown"
        )

        content = f"""
            <article class="info-window">
                {media_html}
                <p class="popup-kicker">{html.escape(popup_mode)}</p>
                <h2>{html.escape(heading)}</h2>
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
                "photo_fallback_url": google_search_url(f"{name} Chicago historic building"),
            }
        )

    return markers


def get_google_maps_api_key() -> str:
    try:
        secret_key = st.secrets.get("GOOGLE_MAPS_API_KEY", "")
    except (FileNotFoundError, KeyError, AttributeError):
        secret_key = ""

    if not secret_key:
        local_secrets_path = APP_DIR / ".streamlit" / "secrets.toml"
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


data = load_lost_chicago()

st.title("Lost Chicago Places")
st.caption("Demolished, transformed, or vanished Chicago places from Lost_Chicago.csv.")

with st.sidebar:
    st.header("Map controls")

    types = sorted(data["type"].dropna().unique())
    neighborhoods = sorted(data["neighborhood"].dropna().unique())

    selected_types = st.multiselect("Type", types, default=types)
    selected_neighborhoods = st.multiselect(
        "Neighborhood",
        neighborhoods,
        default=neighborhoods,
    )

    min_year = int(data["year demolished"].min())
    max_year = int(data["year demolished"].max())
    year_range = st.slider(
        "Year demolished",
        min_value=min_year,
        max_value=max_year,
        value=(min_year, max_year),
    )
    include_unknown_years = st.checkbox("Include unknown demolition years", value=True)
    popup_mode = st.radio(
        "Pin information",
        ["Demolished", "Replacement"],
        horizontal=True,
    )

year_matches = data["year demolished"].between(year_range[0], year_range[1], inclusive="both")
if include_unknown_years:
    year_matches = year_matches | data["year demolished"].isna()

filtered = data[data["type"].isin(selected_types) & data["neighborhood"].isin(selected_neighborhoods) & year_matches]

mapped = filtered.dropna(subset=["lat", "lon"]).copy()
unmapped = filtered[filtered[["lat", "lon"]].isna().any(axis=1)].copy()

metric_1, metric_2, metric_3 = st.columns(3)
metric_1.metric("Filtered places", len(filtered))
metric_2.metric("Mapped pins", len(mapped))
metric_3.metric("Missing coordinates", len(unmapped))

st.subheader("Structure Type Breakdown")
breakdown = structure_breakdown(filtered)

if breakdown.empty:
    st.info("No structure types match the current filters.")
else:
    sunburst = px.sunburst(
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
    sunburst.update_traces(
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
    sunburst.update_layout(
        hoverlabel=dict(bgcolor="#111827", font_color="#ffffff", font_size=13),
        margin=dict(t=10, r=10, b=10, l=10),
        height=560,
        hovermode="closest",
        uniformtext=dict(minsize=11, mode="hide"),
    )
    st.plotly_chart(sunburst, width="stretch")
    st.caption(
        "The middle ring groups places by structure type. The outer ring breaks each "
        "structure type into causes of loss; larger slices represent more places in "
        "the current filters. Hover over any slice to see its count and share."
    )

    with st.expander("Structure type counts", expanded=False):
        st.dataframe(
            breakdown.rename(
                columns={
                    "structure_type": "Structure type",
                    "loss_cause": "Cause",
                    "places": "Lost places",
                }
            ),
            width="stretch",
            hide_index=True,
        )

st.subheader("Causes of Loss by Replacement Category")
loss_breakdown = cause_replacement_breakdown(filtered)

if loss_breakdown.empty:
    st.info("No cause and replacement category records match the current filters.")
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
    loss_chart = go.Figure(
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
    loss_chart.update_layout(
        height=max(520, 58 * len(cause_order)),
        hoverlabel=dict(bgcolor="#111827", font_color="#ffffff", font_size=13),
        margin=dict(t=20, r=20, b=130, l=130),
        xaxis=dict(side="top", tickangle=35, title="Replacement category"),
        yaxis=dict(autorange="reversed", title="Cause of loss"),
    )
    st.plotly_chart(loss_chart, width="stretch")
    st.caption(
        "Each cell shows how many places share a cause of loss and replacement "
        "category. Darker cells indicate more places; hover for the count and "
        "share within that cause."
    )

    with st.expander("Cause and replacement category counts", expanded=False):
        st.dataframe(
            loss_breakdown.rename(
                columns={
                    "loss_cause": "Cause of demolition",
                    "replacement_category": "Replacement category",
                    "places": "Lost places",
                    "total_places": "Cause total",
                    "share_of_cause": "Share of cause",
                }
            )[
                [
                    "Cause of demolition",
                    "Replacement category",
                    "Lost places",
                    "Cause total",
                    "Share of cause",
                ]
            ],
            width="stretch",
            hide_index=True,
        )

if mapped.empty:
    st.warning("No rows with coordinates match the current filters.")
else:
    google_maps_api_key = get_google_maps_api_key()
    if google_maps_api_key:
        components.html(
            google_maps_html(
                marker_payload(mapped, popup_mode, google_maps_api_key),
                google_maps_api_key,
            ),
            height=700,
            scrolling=False,
        )
    else:
        st.error("Add a Google Maps API key to display the interactive Google map.")
        st.code('GOOGLE_MAPS_API_KEY = "your-api-key"', language="toml")

with st.expander("Mapped place data", expanded=False):
    st.dataframe(
        mapped[
            [
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
        ],
        width="stretch",
        hide_index=True,
    )

if not unmapped.empty:
    with st.expander("Rows missing coordinates", expanded=True):
        st.dataframe(
            unmapped[
                [
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
            ],
            width="stretch",
            hide_index=True,
        )
