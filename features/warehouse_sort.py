import streamlit as st
import pandas as pd
from itertools import combinations

# ================================
# 📥 LOAD USER DATA
# ================================
def load_user_data():
    uploaded_file = st.file_uploader(
        "Upload your shipment data (.xlsx)",
        type=["xlsx"]
    )

    if uploaded_file is None:
        return None

    try:
        data = pd.read_excel(uploaded_file)

        required_cols = ["DestZip", "Volume"]
        missing_cols = [col for col in required_cols if col not in data.columns]

        if missing_cols:
            st.error(f"Missing required columns: {missing_cols}")
            return None
        
        data["Volume"] = pd.to_numeric(data["Volume"], errors="coerce").fillna(1)

        # Keep only the 5-digit ZIP portion before any hyphen
        data["DestZip"] = data["DestZip"].astype(str).str.split("-").str[0]

        # Pad to standard 5-digit ZIP format
        data["DestZip"] = data["DestZip"].str.zfill(5)

        # Create 3-digit ZIP prefix
        data["Dest3"] = data["DestZip"].str[:3]

        st.success("File uploaded successfully ✅")
        #st.dataframe(data.head())

        return data

    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None


# ================================
# 📂 LOAD STATIC FILES
# ================================
@st.cache_data
def load_static_data():
    try:
        maersk_zones = pd.read_excel("assets/Maersk Zones.xlsx")
        warehouse_sorting_loc = pd.read_excel("assets/Warehouse & Sorting Locations.xlsx")
        maersk_tnt = pd.read_excel("assets/Service TNT.xlsx")

        maersk_zones["Set_ID"] = (
            maersk_zones["Set_ID"]
            .astype(int)      # ensure numeric first
            .astype(str)
            .str.zfill(3)
        )

        warehouse_sorting_loc["Zip"] = warehouse_sorting_loc["Zip"].astype(str).str.zfill(5)
        warehouse_sorting_loc["ThreeOriginZip"] = warehouse_sorting_loc["Zip"].str[:3]

        return maersk_zones, warehouse_sorting_loc, maersk_tnt

    except Exception as e:
        st.error(f"Error loading static files: {e}")
        return None, None, None


# ================================
# 🗺️ BUILD ZONE LOOKUP
# ================================
@st.cache_data
def build_zone_lookup(maersk_zones, origins):
    rows = []

    filtered = maersk_zones[maersk_zones["Set_ID"].isin(origins)]

    for _, r in filtered.iterrows():
        origin = str(r["Set_ID"]).zfill(3)

        for dest in range(int(r["Min_Zip_Int"]), int(r["Max_Zip_Int"]) + 1):
            rows.append({
                "ID": f"{origin}-{str(dest).zfill(3)}",
                "Zone": r["Zone"]
            })

    return pd.DataFrame(rows)


# ================================
# 🔗 MAP ZONES TO DATA
# ================================
def add_zone_columns(data, zone_lookup, warehouse_df):

    zone_dict = dict(zip(zone_lookup["ID"], zone_lookup["Zone"]))

    mapping = dict(zip(
        warehouse_df["ThreeOriginZip"],
        warehouse_df["Location"]
    ))

    for origin, location in mapping.items():
        zone_col = f"{location} Zone"

        keys = origin + "-" + data["Dest3"]

        data[zone_col] = keys.map(zone_dict)

    return data



def normalize_zip(zip_code):
    if not zip_code:
        return None

    zip_code = str(zip_code).strip()

    if not zip_code.isdigit():
        return None

    if len(zip_code) == 5:
        return zip_code[:3]
    elif len(zip_code) == 3:
        return zip_code.zfill(3)
    else:
        return None
# ================================
# 📊 OPTIMIZATION ENGINE
# ================================
def evaluate_combinations(data, selected_locations, num_nodes):
    zone_cols = [f"{loc} Zone" for loc in selected_locations]
    results = []

    total_vol = data["Volume"].sum()

    for combo in combinations(zone_cols, num_nodes):

        combo_name = [c.replace(" Zone", "") for c in combo]
        subset = data[list(combo)]

        # Remove rows where all candidate zones are missing
        valid_rows = subset.notna().any(axis=1)

        subset = subset[valid_rows]
        volume_data = data.loc[valid_rows, "Volume"]

        best_zone = subset.min(axis=1)
        weighted_avg = (best_zone * volume_data).sum() / volume_data.sum()

        # Volume split
        winner = subset.idxmin(axis=1)

        volume_split = {}

        for col in combo:
            vol = volume_data.loc[winner == col].sum()
            volume_split[col.replace(" Zone", "")] = round(vol / total_vol * 100, 2)

        results.append({
            "Locations": " | ".join(combo_name),
            "Weighted Avg Zone": round(weighted_avg, 3),
            **volume_split
        })

    results_df = pd.DataFrame(results).sort_values("Weighted Avg Zone").reset_index(drop=True)

    return results_df


# ================================
# 📦 FINAL DISTRIBUTION
# ================================
def build_distribution(data, best_combo):
    best_cols = [f"{loc} Zone" for loc in best_combo]

    data["Best Zone"] = data[best_cols].min(axis=1)

    summary = (
        data.groupby("Best Zone", as_index=False)["Volume"]
        .sum()
    )

    total = summary["Volume"].sum()
    summary["Pct of Total"] = (summary["Volume"] / total * 100).round(2)

    return data, summary


# ================================
# 🚀 MAIN APP
# ================================
def warehouse_sort_app():
    st.header("Warehouse Sorting Tool")
    st.caption("DestZip is Required")

    # ================================
    # LOAD DATA
    # ================================
    maersk_zones, warehouse_df, maersk_tnt = load_static_data()
    if maersk_zones is None:
        return

    data = load_user_data()
    if data is None:
        return

    # ================================
    # SESSION STATE INIT
    # ================================
    if "custom_warehouses" not in st.session_state:
        st.session_state.custom_warehouses = pd.DataFrame(
            columns=["Location", "ThreeOriginZip"]
        )

    if "run_optimization" not in st.session_state:
        st.session_state.run_optimization = False

    # ================================
    # CUSTOM WAREHOUSE FORM (NO RERUNS)
    # ================================
    st.subheader("Add Custom Warehouse (Optional)")

    with st.form("custom_warehouse_form"):

        col1, col2 = st.columns(2)

        with col1:
            custom_name = st.text_input("Custom Location Name")

        with col2:
            custom_zip = st.text_input("ZIP Code (3 or 5 digits)")

        submitted = st.form_submit_button("Add Custom Warehouse")

        if submitted:
            origin_zip = normalize_zip(custom_zip)

            if not custom_name:
                st.error("Please enter a location name")
            elif origin_zip is None:
                st.error("Enter a valid ZIP")
            else:
                existing = pd.concat([
                    warehouse_df["ThreeOriginZip"],
                    st.session_state.custom_warehouses["ThreeOriginZip"]
                ]).tolist()

                # 🚨 DUPLICATE DETECTED
                if origin_zip in existing and not st.session_state.get("confirm_duplicate", False):
                    st.warning(f"ZIP {origin_zip} already exists. Click again to confirm adding duplicate.")

                    st.session_state.confirm_duplicate = True
                    return

                # ✅ ADD WAREHOUSE
                new_row = pd.DataFrame([{
                    "Location": custom_name,
                    "ThreeOriginZip": origin_zip
                }])

                st.session_state.custom_warehouses = pd.concat(
                    [st.session_state.custom_warehouses, new_row],
                    ignore_index=True
                )

                st.session_state.confirm_duplicate = False

                st.success(f"Added: {custom_name} ({origin_zip})")

    # ================================
    # COMBINE WAREHOUSES
    # ================================
    warehouse_only = warehouse_df[
        warehouse_df["Type"].str.strip().str.lower() == "warehouse"
    ]
    
    combined_df = pd.concat(
        [
            warehouse_only[["Location", "ThreeOriginZip"]],
            st.session_state.custom_warehouses
        ],
        ignore_index=True
    )

    if not st.session_state.custom_warehouses.empty:
        st.subheader("Custom Warehouses Added")
        st.dataframe(st.session_state.custom_warehouses)

    # ================================
    # SELECTION UI (NO AUTO RUN)
    # ================================
    st.subheader("Select Warehouses 🏭")

    with st.form("selection_form"):

        locations = combined_df["Location"].tolist()

        selected_locations = st.multiselect(
            "Choose locations:",
            options=locations,
            default=locations[:1]
        )

        num_nodes = st.selectbox("Number of warehouses:", [1, 2, 3])

        optimize_clicked = st.form_submit_button("Optimize")


    # ================================
    # RUN OPTIMIZATION (ONLY ON CLICK)
    # ================================
    if optimize_clicked:

        if len(selected_locations) < num_nodes:
            st.warning("Select enough warehouses")
        else:
            with st.spinner("Running optimization..."):

                data_copy = data.copy()

                selected_df = combined_df[
                    combined_df["Location"].isin(selected_locations)
                ]

                origins = selected_df["ThreeOriginZip"].tolist()

                # Validate origins
                valid_origins = set(maersk_zones["Set_ID"])
                invalid = [o for o in origins if o not in valid_origins]

                if invalid:
                    st.warning(f"Invalid origins not in Maersk zones: {invalid}")

                # Build lookup (cache-friendly)
                origins_tuple = tuple(sorted(origins))
                zone_lookup = build_zone_lookup(maersk_zones, origins_tuple)

                # Map zones
                data_copy = add_zone_columns(data_copy, zone_lookup, selected_df)

                # Optimize
                results_df = evaluate_combinations(data_copy, selected_locations, num_nodes)

            # ================================
            # OUTPUT
            # ================================
            st.subheader("Optimization Results")
            st.dataframe(results_df)

            best_combo = results_df.iloc[0]["Locations"].split(" | ")

            st.success(f"Best Choice: {' & '.join(best_combo)}")

            data_copy, summary = build_distribution(data_copy, best_combo)

            st.subheader("Zone Distribution")
            st.dataframe(summary)
