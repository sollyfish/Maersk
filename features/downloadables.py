import streamlit as st

def downloadables():
    st.header("Important Files from the Pricing Team")

    with open("assets/DAS-EDAS-2026LIST.xlsx", "rb") as f:
        st.download_button(
            label="Download DAS/EDAS 2026 List",
            data=f,
            file_name="DAS-EDAS-2026LIST.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with open("assets/MaerskAppTemplate.xlsx", "rb") as f:
        st.download_button(
            label="Download Maersk App Template",
            data=f,
            file_name="MaerskAppTemplate.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
