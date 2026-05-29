import streamlit as st
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import os
from math import radians, sin, cos, sqrt, atan2
from shapely.geometry import LineString

type_colors = {
    "warehouse": "red",
    "sort": "blue"
}

# ---------------- Resource path (repo-root safe) ----------------
def resource_path(relative_path: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        relative_path
    )

# ---------------- Distance calculation (Haversine) ----------------
def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1))
        * cos(radians(lat2))
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# ---------------- Load warehouses ----------------
@st.cache_data
def load_warehouses():
    df = pd.read_excel(resource_path("assets/Warehouse & Sorting Locations.xlsx"))

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    #st.write(f"Warehouse file columns: {df.columns.tolist()}")

    required_cols = {"building name", "zip", "lat", "lon", "type"}
    if not required_cols.issubset(df.columns):
        raise ValueError(
            f"Warehouse file must contain columns: {required_cols}"
        )

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326"
    )

    return gdf

# ---------------- Load ZIP centroids ----------------
@st.cache_data
def load_zip_centroids():
    df = pd.read_csv(resource_path("assets/Centroids.csv"))

    # Normalize column names
    df.columns = df.columns.str.strip().str.lower()

    required_cols = {"zip", "city", "state", "lat", "long"}
    if not required_cols.issubset(df.columns):
        raise ValueError(
            f"ZIP centroid file must contain columns: {required_cols}"
        )

    df["zip"] = df["zip"].astype(str).str.zfill(5)
    return df

# ---------------- Streamlit Feature Entry Point ----------------
def warehouse_map_app():
    st.header("Nearest Warehouse Map")

    zip_centroids = load_zip_centroids()

    zip_centroids["zip_label"] = (
        zip_centroids["zip"]
        + " – "
        + zip_centroids["city"].str.title()
        + ", "
        + zip_centroids["state"].str.upper()
    )

    zip_label = st.selectbox(
        "Enter a ZIP code",
        options=zip_centroids["zip_label"].sort_values().tolist(),
        index=None,
        placeholder="Start typing ZIP, city, or state..."
    )

    # Load data
    try:
        warehouses = load_warehouses()
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        return

    st.caption(f"{len(warehouses)} warehouses loaded")

    nearest = None
    zip_point = None
    zip_input = None
    if zip_label:
        zip_input = zip_label.split(" – ")[0]
    
    if zip_input:
        if not zip_input.isdigit() or len(zip_input) != 5:
            st.warning("Please enter a valid 5-digit ZIP code.")
        else:
            zip_row = zip_centroids[zip_centroids["zip"] == zip_input]

            if zip_row.empty:
                st.warning("ZIP code not found.")
            else:
                zip_lat = zip_row.iloc[0]["lat"]
                zip_lon = zip_row.iloc[0]["long"]

                zip_point = gpd.GeoDataFrame(
                    {"zip": [zip_input]},
                    geometry=gpd.points_from_xy([zip_lon], [zip_lat]),
                    crs="EPSG:4326"
                )

                warehouses["distance_miles"] = warehouses.apply(
                    lambda r: haversine_miles(
                        zip_lat,
                        zip_lon,
                        r.geometry.y,
                        r.geometry.x
                    ),
                    axis=1
                )
                nearest = (
                    warehouses
                    .sort_values("distance_miles")
                    .groupby("type", group_keys=False)
                    .head(2)
                )
                
                # Build distance lines (ZIP → warehouse)
                lines = []
                for _, row in nearest.iterrows():
                    line = LineString([
                        (zip_lon, zip_lat),
                        (row.geometry.x, row.geometry.y)
                    ])
                    lines.append(line)

                distance_lines = gpd.GeoDataFrame(
                    geometry=lines,
                    crs="EPSG:4326"
                )
    # ---------------- Plot ----------------
    fig, ax = plt.subplots(figsize=(15, 10))
    plt.subplots_adjust(right=0.8)
    # State boundaries
    states = gpd.read_file(
        resource_path("shapefiles/states_preprocessed.gpkg"),
        engine="pyogrio"
    )
    states.boundary.plot(ax=ax, linewidth=0.5, edgecolor="black")

    # Plot all warehouses by type
    for t, group in warehouses.groupby("type"):
        color = type_colors.get(t.lower(), "gray")  # fallback if unexpected value
    
        group.plot(
            ax=ax,
            color=color,
            markersize=60,
            alpha=0.7,
            label=t.title()
        )

    # Highlight nearest warehouses
    if nearest is not None:
        for t, group in nearest.groupby("type"):
            color = type_colors.get(t.lower(), "black")
    
            group.plot(
                ax=ax,
                color=color,
                markersize=150,
                edgecolor="black",  # highlight effect
                linewidth=1.5,
                label=f"Nearest {t.title()}"
            )

    # Plot ZIP point
    if zip_point is not None:
        zip_point.plot(
            ax=ax,
            color="blue",
            markersize=150,
            marker="*",
            label="Input ZIP"
        )
    if nearest is not None:
        distance_lines.plot(
            ax=ax,
            color="blue",
            linewidth=2,
            linestyle="--",
            alpha=0.8
        )

    # Continental US view
    ax.set_xlim(-130, -65)
    ax.set_ylim(24, 50)
    ax.set_aspect("equal", adjustable="box")

    ax.set_title("Warehouse Locations & Nearest Facilities", fontsize=16)
    ax.axis("off")

    handles, labels = ax.get_legend_handles_labels()

    seen = set()
    unique = [(h, l) for h, l in zip(handles, labels)
              if not (l in seen or seen.add(l))]
    ax.legend(
        *zip(*unique),
        loc="center left",
        bbox_to_anchor=(1, 0.5),
        title="Legend",
        frameon=True,
        markerscale=1.3
    )
    plt.tight_layout(rect=[0, 0, 0.8, 1])

    st.pyplot(fig)

    # ---------------- Results Table ----------------
    if nearest is not None:
        st.subheader("📍 Closest Warehouses")

        result_df = (
            nearest[["building name", "distance_miles", "type", "zip"]]
            .assign(distance_miles=lambda d: d["distance_miles"].round(1))
            .rename(columns={"distance_miles": "Distance (miles)"})
            .reset_index(drop=True)
        )

        st.dataframe(result_df)
        st.caption(f"NOTE: Distances are straight-line (Haversine) and do not reflect actual travel distance or time.")

