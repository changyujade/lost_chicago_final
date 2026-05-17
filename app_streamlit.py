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
DATA_PATH = APP_DIR / "LostChicago.csv"
CHICAGO_CENTER = {"lat": 41.8781, "lng": -87.6298}

cause_colors = {
    "Fire":"#d4532a","Urban Renewal":"#4a6741","Private Development":"#5a6e8a",
    "Industrial Decline":"#7a6a5a","Public Housing Policy":"#c89a3c",
    "Public Infrastructure":"#8a7a9a","Executive / Legislative Action":"#3d7a6a",
    "City Growth":"#b87840","Unknown":"#aaaaaa",
}

era_colors = {
    "Early Chicago\n(1837-1948)":"rgba(212,83,42,0.2)",
    "Urban Renewal Era\n(1949-1989)":"rgba(90,110,138,0.2)",
    "Market-Driven Era\n(1990-present)":"rgba(200,154,60,0.2)",
}

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
def load_data() -> pd.DataFrame:
    data = pd.read_csv(DATA_PATH)
    data.columns = data.columns.str.strip()

    data["lat"] = pd.to_numeric(data["lat"], errors="coerce")
    data["lon"] = pd.to_numeric(data["lon"], errors="coerce")
    data["year_built"] = pd.to_numeric(data["year_built"], errors="coerce")
    data["year_demolished"] = pd.to_numeric(data["year_demolished"], errors="coerce")

    # Keep both naming styles because the two merged app sections use different
    # column labels.
    data["year built"] = data["year_built"]
    data["year demolished"] = data["year_demolished"]
    data["Replacement Categories"] = data["replacement_categories"]
    data["Description/Comments"] = data["description"]

    def classify_era(year):
        if pd.isna(year):
            return "Unknown"
        if year <= 1948:
            return "Early Chicago\n(1837-1948)"
        if year <= 1989:
            return "Urban Renewal Era\n(1949-1989)"
        return "Market-Driven Era\n(1990-present)"

    data["era"] = data["year_demolished"].apply(classify_era)
    data["community_area"] = data["neighborhood"]

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

@st.cache_data
def load_geojson():
    with (APP_DIR / "chicago_neighborhoods.geojson").open() as f:
        return json.load(f)

data = load_data()

st.title("Chicago Lost Places")
st.markdown("Explore how Chicago's architectural landscape has changed over the years through a series of visualizations exploring the how's and why's.")
st.divider()


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

st.divider()
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


geojson = load_geojson()
df = data

# Scatter Plot Timeline
fig = go.Figure()

for era_name, x0, x1, bg_color in [
    ("Early Chicago\n(1837-1948)",        1837,   1948.5, era_colors["Early Chicago\n(1837-1948)"]),
    ("Urban Renewal Era\n(1949-1989)",    1948.5, 1989.5, era_colors["Urban Renewal Era\n(1949-1989)"]),
    ("Market-Driven Era\n(1990-present)", 1989.5, 2030,   era_colors["Market-Driven Era\n(1990-present)"]),
]:
    fig.add_vrect(x0=x0, x1=x1, fillcolor=bg_color, layer="below", line_width=1,
                  line_color="rgba(0,0,0,0.1)", annotation_text=era_name,
                  annotation_position="top left", annotation_font=dict(size=10, color="#333"))

POLICY_LINES = [
    (1871, "Great Chicago Fire"),
    (1923, "Chicago Zoning Ordinance"),
    (1949, "Federal Housing Act"),
    (1968, "Chicago Landmarks Ordinance"),
    (1992, "HOPE VI Act"),
]

for year, label in POLICY_LINES:
    fig.add_vline(
        x=year,
        line_dash="dot",
        line_color="black",
        line_width=1.5,
        annotation_text=label,
        annotation_position="bottom right",
        annotation_font=dict(size=9, color="black"),
        annotation_textangle=-90,
    )

for cause in sorted(df["cause"].dropna().unique()):
    cause_df = df[df["cause"] == cause]
    fig.add_trace(go.Scatter(
        x=cause_df["year_demolished"], y=[cause]*len(cause_df),
        mode="markers", name=cause,
        marker=dict(size=13, color=cause_colors.get(cause,"#888888"), symbol="circle", opacity=0.85),
        text=cause_df["name"], customdata=cause_df[["neighborhood","type"]],
        hovertemplate="<b>%{text}</b><br>Year: %{x}<br>Neighborhood: %{customdata[0]}<br>Type: %{customdata[1]}<extra></extra>",
        showlegend=True,
    ))

fig.update_layout(
    title=dict(text="Demolition Timeline: Three Eras of Loss", x=0.5, xanchor="center", font=dict(size=16)),
    xaxis=dict(title="Year Demolished", range=[1837,2030], tickmode="linear", tick0=1840, dtick=20,
               gridcolor="#ddd", gridwidth=0.5, title_font=dict(size=12)),
    yaxis=dict(title="Cause Attributed to Demolition", categoryorder="array",
               categoryarray=sorted(df["cause"].dropna().unique()),
               gridcolor="#ddd", gridwidth=0.5, title_font=dict(size=12)),
    height=650, hovermode="closest", plot_bgcolor="white", paper_bgcolor="white",
    legend=dict(orientation="h", yanchor="top", y=-0.22, xanchor="left", x=0,
                bgcolor="rgba(255,255,255,0.95)", bordercolor="#ccc", borderwidth=1, font=dict(size=9)),
    margin=dict(t=100, b=170, l=130, r=40),
)

st.plotly_chart(fig, width="stretch")

with st.expander("How were these eras divided?"):
    st.markdown("""
**Early Chicago (1837–1948)**
Chicago incorporates as a city in 1837 and begins expanding rapidly as population grows. The Great Fire of 1871 destroys much of the downtown area and forces the city to rebuild with new building codes.

**Urban Renewal Era (1949–1989)**
The 1949 Federal Housing Act marks the start of the urban renewal era, with demolitions peaking under Mayor Daley in the 1960s–70s. This period brought new high-rise projects, university expansions, and public housing developments after the city deployed eminent domain to clear the land and sell it to private developers.

**Market-Driven Era (1990–present)**
Following the neoliberal policies in the mid-1980s, the 1992 HOPE VI Act marks the start of the market-driven demolition era. Signs of gentrification start showing as private development accelerates the displacement of historic buildings and communities.
    """)

with st.expander("Policy Impacts"):
    st.markdown("""
**1871 — Great Chicago Fire**
The fire destroyed approximately one third of the city, leading to adoption of new fire safety construction codes, introduction of skyscrapers, and a building boom in efforts to rebuild the city.

**1923 — Chicago Zoning Ordinance**
Chicago's first comprehensive zoning law fundamentally reshaped the city's landscape by legally separating residential, commercial, and industrial areas. It led to the demolition of mixed-use buildings and established development patterns like vertical growth as well as racial and economic segregation.

**1949 — Federal Housing Act**
Funded urban renewal and slum clearance while allowing cleared land to be sold to private developers at subsidized prices, leading to a spike in both Urban Renewal and Private Development losses through the 1970s.

**1968 — Chicago Landmarks Ordinance**
Passed in direct response to the demolition of historical structures like the Chicago Federal Building and the Garrick Theatre, this ordinance established the Commission on Chicago Landmarks and created the city's first legal framework for designating and protecting landmarks.

**1992 — HOPE VI Act**
Shifted federal housing policy from maintaining high-rise public housing to demolishing it in favor of mixed-income developments. This led to a wave of demolitions in the 1990s and early 2000s, particularly in neighborhoods with large public housing complexes, and accelerated gentrification in many areas.
    """)

st.divider()

# Neighborhood Concentration Chloropleth
st.subheader("Neighborhood Concentration of Losses")
st.markdown("Darker neighborhoods indicate a higher concentration of documented landmark losses. Hover over a neighborhood to see how many structures were lost there.")

area_counts = df.groupby("community_area").size().reset_index(name="losses")

geojson_neighborhoods = []
for feature in geojson['features']:
    geojson_neighborhoods.append(feature['properties']['pri_neigh'])

all_neighborhoods = pd.DataFrame({
    'neighborhood': geojson_neighborhoods,
    'losses': 0
})

for _, row in area_counts.iterrows():
    mask = all_neighborhoods['neighborhood'].str.lower() == row['community_area'].lower()
    if mask.any():
        all_neighborhoods.loc[mask, 'losses'] = row['losses']

fig_map = px.choropleth_map(
    all_neighborhoods,
    geojson=geojson,
    locations='neighborhood',
    featureidkey="properties.pri_neigh",
    color='losses',
    color_continuous_scale="BuPu",
    range_color=(0, max(all_neighborhoods['losses'].max(), 1)),
    map_style="carto-positron",
    zoom=10,
    center={"lat": 41.8781, "lon": -87.6298},
    opacity=0.7,
    hover_data={'neighborhood': True, 'losses': True},
    labels={'losses': 'Lost Landmarks', 'neighborhood': 'Neighborhood'}
)

fig_map.update_layout(
    height=560,
    margin={"r":0, "t":0, "l":0, "b":0},
    hoverlabel=dict(bgcolor="white", font_size=12)
)

st.plotly_chart(fig_map, width="stretch")

st.divider()

# Before and After Visualization
st.subheader("Mapping the Before and After")
st.markdown("Click any marker to learn more about a specific cultural site that was lost and see what occupies the site now.")
 
mapped = df.dropna(subset=["lat", "lon"]).copy()
 
# Jitter duplicate coordinates slightly to prevent markers from stacking directly on top of one another
import numpy as np
coord_counts = {}
markers_json = []
 
for idx, (_, row) in enumerate(mapped.iterrows()):
    name        = str(row.get("name", "Unknown"))
    replacement = str(row.get("replacement", "Unknown"))
    description = str(row.get('description', 'Unknown')).strip('"')
    source = str(row.get("source", ""))
    source_html = f'<a href="{source}" target="_blank" style="font-size:12px;display:block;">Source</a>' if source and source != "nan" else ""
    img = str(row.get("img_link", ""))
    current_img = str(row.get("current_img", ""))
    if current_img and current_img != "nan":
        current_img_html = f'<img src="{current_img}" width="100%" style="border-radius:4px;margin-bottom:6px;">'
    else:
        current_img_html = '<p style="font-size:12px;color:#888;">No photo available</p>'
    marker_id   = f"m_{idx}"
 
    base_lat = float(row["lat"])
    base_lon = float(row["lon"])
    key = (base_lat, base_lon)
 
    # Track how many markers share this coordinate and apply a small offset to each subsequent one
    count = coord_counts.get(key, 0)
    coord_counts[key] = count + 1
 
    if count > 0:
        angle  = count * 2.4          
        radius = 0.00025 * ((count + 1) // 2)
        display_lat = base_lat + radius * np.sin(angle)
        display_lon = base_lon + radius * np.cos(angle)
    else:
        display_lat = base_lat
        display_lon = base_lon
 
    popup_html = f"""
    <div id="{marker_id}" class="lost-place-popup">
        <div id="{marker_id}_historic">
            <h3>{name}</h3>
            <img src="{img}" class="popup-site-image" onerror="this.style.display='none'">
            <p><b>Neighborhood:</b> {row.get('neighborhood', 'Unknown')}</p>
            <p><b>Type:</b> {row.get('type', 'Unknown')}</p>
            <p><b>Demolished:</b> {row.get('year_demolished', 'Unknown')}</p>
            <p><b>Cause:</b> {row.get('cause', 'Unknown')}</p>
            <p><b>Description:</b> {description}</p>
            {source_html}
            <button onclick="document.getElementById('{marker_id}_historic').style.display='none';document.getElementById('{marker_id}_current').style.display='block'"
                class="popup-toggle-button popup-toggle-button-lost">
                Click to See What Replaced It
            </button>
        </div>
        <div id="{marker_id}_current" style="display:none">
            <h3>{replacement}</h3>
            {current_img_html}
            <p><b>Replacement Type:</b> {row.get('replacement_categories', 'Unknown')}</p>
            <div style="margin-top:8px;">
                <button onclick="document.getElementById('{marker_id}_historic').style.display='block';document.getElementById('{marker_id}_current').style.display='none'"
                    class="popup-toggle-button popup-toggle-button-current">
                    Click to See What Was Lost
                </button>
            </div>
        </div>
    </div>
    """
 
    markers_json.append({
        "lat": display_lat,
        "lon": display_lon,
        "title": name,
        "popup": popup_html
    })
 
map_html = f"""
<!DOCTYPE html>
<html>
<head>
    <link href="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.css" rel="stylesheet">
    <script src="https://unpkg.com/maplibre-gl@3.6.2/dist/maplibre-gl.js"></script>
    <style>
        body, html, #map {{ margin: 0; padding: 0; height: 100%; width: 100%; }}
        .maplibregl-popup-content {{
            border-radius: 8px;
            box-sizing: border-box;
            max-height: min(68vh, 480px);
            max-width: 320px;
            overflow-y: auto;
            padding: 12px;
        }}
        .lost-place-popup {{
            box-sizing: border-box;
            font-family: sans-serif;
            max-width: 280px;
            min-width: 220px;
        }}
        .lost-place-popup h3 {{
            font-size: 14px;
            margin: 0 0 6px;
        }}
        .lost-place-popup p {{
            font-size: 12px;
            line-height: 1.35;
            margin: 2px 0;
        }}
        .lost-place-popup a {{
            display: block;
            font-size: 12px;
            margin-top: 6px;
        }}
        .popup-site-image,
        .lost-place-popup img {{
            border-radius: 4px;
            display: block;
            margin-bottom: 6px;
            max-height: 150px;
            object-fit: cover;
            width: 100%;
        }}
        .popup-toggle-button {{
            border: none;
            border-radius: 4px;
            color: white;
            cursor: pointer;
            font-size: 11px;
            margin-top: 8px;
            padding: 4px 10px;
        }}
        .popup-toggle-button-lost {{ background: #d4532a; }}
        .popup-toggle-button-current {{ background: #5a6e8a; }}
    </style>
</head>
<body>
    <div id="map"></div>
    <script>
        const map = new maplibregl.Map({{
            container: 'map',
            style: 'https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json',
            center: [{CHICAGO_CENTER["lng"]}, {CHICAGO_CENTER["lat"]}],
            zoom: 11
        }});
 
        map.addControl(new maplibregl.NavigationControl());
 
        const markers = {json.dumps(markers_json)};
 
        markers.forEach(m => {{
            new maplibregl.Marker({{ color: '#d4532a' }})
                .setLngLat([m.lon, m.lat])
                .setPopup(new maplibregl.Popup({{ maxWidth: '300px' }}).setHTML(m.popup))
                .addTo(map);
        }});

        document.addEventListener('wheel', (event) => {{
            if (event.target.closest('.maplibregl-popup-content')) {{
                event.stopPropagation();
            }}
        }}, {{ capture: true }});

        document.addEventListener('touchmove', (event) => {{
            if (event.target.closest('.maplibregl-popup-content')) {{
                event.stopPropagation();
            }}
        }}, {{ capture: true }});
    </script>
</body>
</html>
"""

st.iframe(map_html, height=700)

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
