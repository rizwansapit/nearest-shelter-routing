"""Streamlit entry point for the Nearest Shelter Routing System."""

from __future__ import annotations

import streamlit as st


st.set_page_config(
    page_title="Nearest Shelter Routing",
    page_icon="🗺️",
    layout="wide",
)

st.title("Nearest Shelter Routing System")

st.success("Python and Streamlit environment configured successfully.")

st.markdown(
    """
    This application will calculate the shortest road-network route
    from a selected starting location to the nearest shelter.

    **Core MVP stack**

    - Python
    - Streamlit
    - PostgreSQL
    - PostGIS
    - pgRouting
    """
)