"""Verify that the project's main Python dependencies are available."""

from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, version


PACKAGES: dict[str, str] = {
    "streamlit": "streamlit",
    "folium": "folium",
    "streamlit-folium": "streamlit_folium",
    "psycopg": "psycopg",
    "SQLAlchemy": "sqlalchemy",
    "GeoAlchemy2": "geoalchemy2",
    "geopandas": "geopandas",
    "python-dotenv": "dotenv",
    "pytest": "pytest",
}


def check_package(package_name: str, import_name: str) -> bool:
    """Import a package and display its installed version."""

    try:
        importlib.import_module(import_name)
        installed_version = version(package_name)
    except (ImportError, PackageNotFoundError) as error:
        print(f"[FAILED] {package_name}: {error}")
        return False

    print(f"[OK] {package_name} {installed_version}")
    return True


def main() -> None:
    """Check all required project packages."""

    print("Checking Nearest Shelter Routing dependencies...\n")

    results = [
        check_package(package_name, import_name)
        for package_name, import_name in PACKAGES.items()
    ]

    print()

    if all(results):
        print("Environment check completed successfully.")
        return

    raise SystemExit(
        "Environment check failed. Install the missing dependencies."
    )


if __name__ == "__main__":
    main()