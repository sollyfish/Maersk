from streamlit.components.v1 import html
from folium.plugins import HeatMap
import geopandas as gpd
import streamlit as st
import pandas as pd
import folium as fm
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from textwrap import dedent

# ================================
# 📂 LOAD GEOSPATIAL FILES (CACHED)
# ================================
@st.cache_data
def load_zip3_shapes():
    gdf = gpd.read_file("shapefiles/zip3_simplified.gpkg")

    # Normalize column names
    gdf.columns = [c.upper() for c in gdf.columns]

    # 🔥 CRITICAL: Set geometry column
    if "GEOMETRY" in gdf.columns:
        gdf = gdf.set_geometry("GEOMETRY")
    else:
        st.error("No GEOMETRY column found")
        st.write(gdf.columns)
        return None

    # Clean ZIP3
    gdf["ZIP3"] = gdf["ZIP3"].astype(str).str.zfill(3)

    return gdf

# ================================
# 📂 LOAD DAS/EDAS List (CACHED)
# ================================
@st.cache_data
def load_das_edas():
    df = pd.read_excel(
        "assets/DAS-EDAS-2026LIST.xlsx",
        skiprows=1
    )

    df.columns = [str(c).strip().lower() for c in df.columns]

    das_zips = (
        df["das"]
        .dropna()
        .astype(float)
        .astype(int)
        .astype(str)
        .str.zfill(5)
        .unique()
    )

    edas_zips = (
        df["edas"]
        .dropna()
        .astype(str)
        .str.zfill(5)
        .unique()
    )

    return set(das_zips), set(edas_zips)

# ================================
# 📥 LOAD USER DATA
# ================================
def load_heatmap_data():
    uploaded_file = st.file_uploader(
        "Upload your shipment data (.xlsx)",
        type=["xlsx"],
        key="heatmap_upload"
    )

    if uploaded_file is None:
        return None
        
    try:
        data = pd.read_excel(uploaded_file)
        data.columns = [c.strip().lower() for c in data.columns]

        required_cols = ["destzip", "volume"]
        missing = [c for c in required_cols if c not in data.columns]

        if missing:
            st.error(f"Missing required columns: {missing}")
            return None

        data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(1)

        # Normalize destination ZIPs
        data["destzip"] = (
            data["destzip"]
            .astype(str)
            .str.strip()
            .str.split("-").str[0]      # remove ZIP+4
            .str.extract(r"(\d+)", expand=False)  # keep digits only
            .str.zfill(5)
        )

        # Create ZIP3
        data["dest3"] = data["destzip"].str[:3]

        st.subheader("📊 Data Summary")
        
        # ================================
        # 🧮 PREP DATA
        # ================================
        
        # Ensure proper formatting
        data["originzip"] = (
            data["originzip"]
            .astype(str)
            .str.strip()
            .str.split("-").str[0]
            .str.extract(r"(\d+)", expand=False)
            .str.zfill(5)
        )


        # ================================
        # PRE-CALCULATIONS
        # ================================
        
        # Volume
        total_volume = data["volume"].sum()
        
        # Weight
        weights = None
        weight_col = None
        if "weight" in data.columns:
            weight_col = "weight"
        elif "actualwt" in data.columns:
            weight_col = "actualwt"
        
        if weight_col:
            weights = pd.to_numeric(data[weight_col], errors="coerce").dropna()
        
        # Dimensions
        top_dim = "N/A"
        if all(col in data.columns for col in ["length", "width", "height"]):
            dims = data[["length", "width", "height"]].copy()
            for col in ["length", "width", "height"]:
                dims[col] = pd.to_numeric(dims[col], errors="coerce")
            dims = dims.dropna()
        
            if not dims.empty:
                dims["dim_str"] = (
                    dims["length"].astype(int).astype(str) + "x" +
                    dims["width"].astype(int).astype(str) + "x" +
                    dims["height"].astype(int).astype(str)
                )
                dim_counts = dims["dim_str"].value_counts()
                top_dim = dim_counts.index[0]

        das_zips, edas_zips = load_das_edas()

        # Make sure destzip is clean
        data["destzip"] = data["destzip"].astype(str).str.zfill(5)
        
        def classify_zip(z):
            if z in edas_zips:
                return "EDAS"
            elif z in das_zips:
                return "DAS"
            else:
                return "None"
        
        data["das_type"] = data["destzip"].apply(classify_zip)
        
        das_counts = data.groupby("das_type")["volume"].sum()
        
        # ================================
        # 📊 KPI METRICS (with charts)
        # ================================
        
        # ================================
        # 📊 KPI GRID (2x2)
        # ================================
        
        row1_col1, row1_col2, row1_col3 = st.columns([2, 0.5, 1.5])
        row2_col1, row2_col2 = st.columns(2)
                        
        
        # -------------------------------
        # 📦 Total Volume (trend or distribution)
        # -------------------------------
        with row1_col1:
            st.subheader("DAS / EDAS")
        
            if not das_counts.empty:

                pie_df = das_counts.reset_index()
                pie_df.columns = ["type", "count"]

                fig, ax = plt.subplots(figsize=(6, 3))

                color_map = {
                    "DAS": "#42B0D5", 
                    "EDAS": "#0E4F6A",
                    "None": "#949494"
                }
                
                colors = [color_map.get(t, "#9E9E9E") for t in pie_df["type"]]
                
                # Create pie WITHOUT labels (we'll use legend instead)
                wedges, _, autotexts = ax.pie(
                    pie_df["count"],
                    labels=None,
                    autopct="%1.1f%%",
                    pctdistance=0.7,
                    radius=0.75,
                    textprops={"fontsize": 11, "weight": "bold"},
                    wedgeprops=dict(width=0.4),
                    colors=colors
                )
                
                # 🔥 Dynamic text color based on brightness
                def is_light(color):
                    r, g, b = mcolors.to_rgb(color)
                    # perceived brightness formula
                    brightness = 0.299*r + 0.587*g + 0.114*b
                    return brightness > 0.6
                
                for i, autotext in enumerate(autotexts):
                    if is_light(colors[i]):
                        autotext.set_color("black")
                    else:
                        autotext.set_color("white")
                
                # ✅ Add legend
                ax.legend(
                    wedges,
                    pie_df["type"],
                    title="Type",
                    loc="center left",
                    bbox_to_anchor=(1, 0.5),
                    frameon=False,          # 🔥 removes the box
                    fontsize=10,
                    title_fontsize=11
                )
                
                ax.set_ylabel("")
                plt.tight_layout()
                fig.subplots_adjust(right=0.8)
                st.pyplot(fig, use_container_width=False)
            else:
                st.write("No ZIP classification available")

        with row1_col3:
            st.subheader("Key Details")
            
            avg_weight_display = (
                f"{weights.mean():,.2f} lbs"
                if weights is not None and not weights.empty
                else "N/A"
            )
        
            st.markdown("""
            <style>
            .kpi-wrapper {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }
            
            .kpi-card {
                background: var(--secondary-background-color);
                color: var(--text-color);
                border-radius: 10px;
                padding: 8px;
            }
            
            .kpi-value {
                font-size: 48px;
                font-weight: 600;
            }
            
            .kpi-label {
                font-size: 18px;
                opacity: 0.7;
            }
            </style>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div class="kpi-wrapper">
            <div class="kpi-card">
            <div class="kpi-value">{int(total_volume):,}</div>
            <div class="kpi-label">Total Volume</div>
            </div>
            
            <div class="kpi-card">
            <div class="kpi-value">{avg_weight_display}</div>
            <div class="kpi-label">Average Weight</div>
            </div>
            </div>
            """, unsafe_allow_html=True)
                    
        # -------------------------------
        # ⚖️ Weight Distribution
        # -------------------------------
        with row2_col1:
            st.subheader("Weight Distribution")
        
            if weight_col:
        
                # Define bins and labels
                bins = [-float("inf"), 1, 5, 10, 20, 30, float("inf")]
                labels = ["<1 lb", "1–5", "6–10", "11–20", "21–30", "31+"]
        
                weight_buckets = pd.cut(weights, bins=bins, labels=labels, right=True)

                weight_buckets = weight_buckets.astype(
                    pd.CategoricalDtype(categories=labels, ordered=True)
                )
        
                bucket_counts = (
                    weight_buckets.value_counts()
                    .reindex(labels)
                    .fillna(0)
                    .astype(int)
                )

                weight_df = bucket_counts.reset_index()
                weight_df.columns = ["bucket", "count"]
                        
                weight_df["bucket"] = pd.Categorical(
                    weight_df["bucket"],
                    categories=labels,
                    ordered=True
                )
                
                weight_df = weight_df.sort_values("bucket")
                fig, ax = plt.subplots(figsize=(6, 3))

                ax.bar(weight_df["bucket"], weight_df["count"], color="#42B0D5")
                
                ax.set_xlabel("")
                ax.set_ylabel("")
                ax.set_title("")
                
                # Clean look
                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                
                plt.xticks(rotation=0)
                
                st.pyplot(fig, use_container_width=False)
    
            else:
                st.write("N/A")
        
        # -------------------------------
        # 📐 Dimension Distribution
        # -------------------------------
        with row2_col2:
            st.subheader("Top 5 Dimensions")
        
            if all(col in data.columns for col in ["length", "width", "height"]):
                dims = data[["length", "width", "height"]].copy()
        
                for col in ["length", "width", "height"]:
                    dims[col] = pd.to_numeric(dims[col], errors="coerce")
        
                dims = dims.dropna()
        
                if not dims.empty:
                    dims["dim_str"] = (
                        dims["length"].astype(int).astype(str) + "x" +
                        dims["width"].astype(int).astype(str) + "x" +
                        dims["height"].astype(int).astype(str)
                    )
        
                    dim_counts = dims["dim_str"].value_counts()
        
                    # Top 5 (already sorted descending)
                    top5 = dim_counts.head(5)
                    
                    # Everything else
                    other_sum = dim_counts.iloc[5:].sum()
                    
                    # Build final series
                    if other_sum > 0:
                        final_dims = pd.concat([
                            top5,
                            pd.Series({"Other": other_sum})
                        ])
                    else:
                        final_dims = top5
                    
                    # 👇 FORCE correct order
                    top_part = final_dims.drop("Other", errors="ignore").sort_values(ascending=False)
                    
                    if "Other" in final_dims:
                        final_dims = pd.concat([top_part, final_dims.loc[["Other"]]])
                    else:
                        final_dims = top_part
                    
                    # Convert to DataFrame
                    dim_df = final_dims.reset_index()
                    dim_df.columns = ["dimension", "count"]
                    
                    # 👇 FORCE ORDER (this is the missing piece)
                    dim_df["dimension"] = pd.Categorical(
                        dim_df["dimension"],
                        categories=dim_df["dimension"].tolist(),  # preserves current order
                        ordered=True
                    )
                    
                    dim_df = dim_df.sort_values("dimension")
                    fig, ax = plt.subplots(figsize=(6, 3))

                    ax.bar(dim_df["dimension"], dim_df["count"], color="#42B0D5")
                    
                    ax.set_xlabel("")
                    ax.set_ylabel("")
                    ax.set_title("")
                    
                    # Clean look
                    ax.spines["top"].set_visible(False)
                    ax.spines["right"].set_visible(False)
                    
                    plt.xticks(rotation=0)
                    
                    st.pyplot(fig, use_container_width=False)
        
                    
                else:
                    st.write("No valid dimensions")
            else:
                st.write("N/A")
        
        # ================================
        # 📦 VOLUME BY ORIGIN (TOP 5 + OTHER)
        # ================================
        
        if "originzip" in data.columns:
        
            vol_by_origin = (
                data.groupby("originzip")["volume"]
                .sum()
                .reset_index()
                .sort_values(by="volume", ascending=False)
            )
        
            total_volume = vol_by_origin["volume"].sum()
        
            # Top 5
            top5 = vol_by_origin.head(5).copy()
        
            # Remaining = "Other"
            if len(vol_by_origin) > 5:
                other_volume = vol_by_origin.iloc[5:]["volume"].sum()
        
                other_row = pd.DataFrame({
                    "originzip": ["Other"],
                    "volume": [other_volume]
                })
        
                final_df = pd.concat([top5, other_row], ignore_index=True)
            else:
                final_df = top5

            # Sort so "Other" stays at bottom naturally
            final_df = final_df.sort_values(
                by="volume",
                ascending=False
            ).reset_index(drop=True)
            
            # Calculate %
            final_df["Volume %"] = (final_df["volume"] / total_volume) * 100
        
            # Format
            final_df["Volume %"] = final_df["Volume %"].map(lambda x: f"{x:.1f}%")
            final_df["Volume"] = final_df["volume"].map(lambda x: f"{x:,.0f}")
        
            # Display
            st.markdown("### 📍 Volume by Origin (Top 5 + Other)")
            st.dataframe(final_df, use_container_width=True)

        return data

    except Exception as e:
        import traceback
        st.error(traceback.format_exc())
        return None


# ================================
# 🗺️ MAIN APP
# ================================
def heatmap_app():

    st.header("Data Summary and Heatmap Tool 🗺️")
    st.caption("PLD Data Columns can include: OriginZip, DestZip, Weight, Length, Width, Height, Volume")

    # Load user data
    data = load_heatmap_data()
    if data is None:
        return


    # ================================
    # HEATMAP BUTTON
    # ================================
    if st.button("Generate Heatmap"):

        with st.spinner("Building heatmap..."):

            progress = st.progress(0)

            # Load geospatial data
            zip3_shapes = load_zip3_shapes()

            progress.progress(20)

            # Aggregate to ZIP3
            agg = (
                data.groupby("dest3", as_index=False)["volume"]
                .sum()
            )

            progress.progress(40)

            # Merge with geometry
            gdf = pd.merge(
                agg,
                zip3_shapes,
                left_on="dest3",
                right_on="ZIP3",
                how="left"
            )

            gdf = gdf.dropna(subset=["GEOMETRY"])

            progress.progress(60)
            
            gdf["log_volume"] = gdf["volume"].apply(lambda v: np.log10(max(v, 1)))
            # Create map
            m = fm.Map(location=[39.5, -98.35], zoom_start=4)

            # Normalize (0–1 scale)
            min_val = gdf["log_volume"].min()
            max_val = gdf["log_volume"].max()
            
            if max_val == min_val:
                gdf["log_volume_norm"] = 1
            else:
                gdf["log_volume_norm"] = (gdf["log_volume"] - min_val) / (max_val - min_val)
                
            # Build heat data
            heat_data = []
            
            for _, row in gdf.iterrows():
                geom = row["GEOMETRY"]
            
                if geom is not None and geom.is_valid:
                    centroid = geom.centroid
            
                    heat_data.append([
                        centroid.y,
                        centroid.x,
                        row["log_volume_norm"]
                    ])

            progress.progress(80)

            # Add heatmap layer
            HeatMap(
                heat_data,
                radius=20,
                blur=10,
                min_opacity=0.2,
                gradient={
                    0.2: "blue",
                    0.4: "cyan",
                    0.6: "lime",
                    0.8: "yellow",
                    1.0: "red"
                }
            ).add_to(m)

            progress.progress(100)

            # Save HTML to session
            st.session_state["heatmap_html"] = m.get_root().render()

        st.success("Heatmap ready!")

    # ================================
    # DISPLAY + DOWNLOAD
    # ================================
    if "heatmap_html" in st.session_state:

        st.components.v1.html(
            st.session_state["heatmap_html"],
            height=900
        )

