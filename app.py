import streamlit as st

from features.zone_map import zone_map_app
from features.warehouse_map import warehouse_map_app
from features.warehouse_sort import warehouse_sort_app
from features.heatmap import heatmap_app
from features.downloadables import downloadables

st.set_page_config(
    page_title="Pricing Tools",
    layout="wide"
)

st.title("📊 Pricing Team Tools (for Other Teams)")

menu = st.sidebar.radio(
    "Select a Tool",
    ["Maersk Zone Map & List", "Nearest Warehouse Map", "Warehouse Sort", "Client Summary & Heatmap", "Download Important Files"]
)

if menu == "Maersk Zone Map & List":
    zone_map_app()

elif menu == "Nearest Warehouse Map":
    warehouse_map_app()

elif menu == "Warehouse Sort":
    warehouse_sort_app()

elif menu == "Client Summary & Heatmap":
    heatmap_app()

elif menu == "Download Important Files":
    downloadables()

