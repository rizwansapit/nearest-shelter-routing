"""Inspect, clean, and import a road dataset into PostGIS."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.engine import Engine


DEFAULT_TARGET_CRS = "EPSG:32650"
DATABASE_SCHEMA = "routing"
DATABASE_TABLE = "roads"

ROAD_NAME_CANDIDATES = (
    "road_name",
    "name",
    "street_name",
    "street",
    "ref",
)

ROAD_TYPE_CANDIDATES = (
    "road_type",
    "highway",
    "fclass",
    "class",
    "type",
    "category",
)


def parse_arguments() -> argparse.Namespace:
    """Read command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Inspect, clean, and import road geometries into PostGIS."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Path to the road vector dataset.",
    )

    parser.add_argument(
        "--target-crs",
        default=DEFAULT_TARGET_CRS,
        help=(
            "Projected CRS used for road lengths. "
            f"Default: {DEFAULT_TARGET_CRS}"
        ),
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/road_data_report.json"),
        help="Output path for the JSON data-quality report.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect and clean the data without loading it into PostGIS.",
    )

    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace routing.roads when the table already exists.",
    )

    return parser.parse_args()


def get_required_environment_variable(name: str) -> str:
    """Return a required environment variable."""

    value = os.getenv(name)

    if not value:
        raise SystemExit(
            f"Missing environment variable: {name}. "
            "Check the local .env file."
        )

    return value


def create_database_engine() -> Engine:
    """Create a SQLAlchemy engine using values from .env."""

    load_dotenv()

    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=get_required_environment_variable("DB_USER"),
        password=get_required_environment_variable("DB_PASSWORD"),
        host=get_required_environment_variable("DB_HOST"),
        port=int(get_required_environment_variable("DB_PORT")),
        database=get_required_environment_variable("DB_NAME"),
    )

    return create_engine(database_url)


def normalise_column_name(column_name: Any) -> str:
    """Return a lowercase and whitespace-free column name."""

    return str(column_name).strip().lower()


def find_column(
    columns: pd.Index,
    candidates: tuple[str, ...],
) -> str | None:
    """Find the first available column matching candidate names."""

    normalised_columns = {
        normalise_column_name(column): str(column)
        for column in columns
    }

    for candidate in candidates:
        if candidate in normalised_columns:
            return normalised_columns[candidate]

    return None


def inspect_source_data(roads: gpd.GeoDataFrame) -> dict[str, Any]:
    """Collect information about the original road dataset."""

    geometry_types = {
        str(geometry_type): int(count)
        for geometry_type, count in (
            roads.geometry.geom_type.value_counts(dropna=False).items()
        )
    }

    return {
        "input_records": int(len(roads)),
        "input_crs": str(roads.crs) if roads.crs else None,
        "input_columns": [str(column) for column in roads.columns],
        "input_geometry_types": geometry_types,
        "null_geometries": int(roads.geometry.isna().sum()),
        "empty_geometries": int(roads.geometry.is_empty.sum()),
        "invalid_geometries": int((~roads.geometry.is_valid).sum()),
    }


def clean_road_data(
    roads: gpd.GeoDataFrame,
    target_crs: str,
) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    """Clean and standardise the road dataset."""

    if roads.crs is None:
        raise SystemExit(
            "The road dataset has no CRS. Assign the correct CRS in QGIS "
            "before running this import. Do not guess the CRS."
        )

    cleaning_statistics: dict[str, int] = {}

    initial_count = len(roads)

    null_or_empty = roads.geometry.isna() | roads.geometry.is_empty

    cleaning_statistics["removed_null_or_empty"] = int(
        null_or_empty.sum()
    )

    roads = roads.loc[~null_or_empty].copy()

    invalid_before = ~roads.geometry.is_valid

    cleaning_statistics["invalid_before_repair"] = int(
        invalid_before.sum()
    )

    if invalid_before.any():
        roads.loc[invalid_before, "geometry"] = (
            roads.loc[invalid_before].geometry.make_valid()
        )

    # Separate MultiLineString and GeometryCollection components.
    roads = roads.explode(
        index_parts=False,
        ignore_index=True,
    )

    line_geometry_mask = roads.geometry.geom_type == "LineString"

    cleaning_statistics["removed_non_line_geometries"] = int(
        (~line_geometry_mask).sum()
    )

    roads = roads.loc[line_geometry_mask].copy()

    duplicate_geometry_mask = (
        roads.geometry.to_wkb().duplicated(keep="first")
    )

    cleaning_statistics["removed_duplicate_geometries"] = int(
        duplicate_geometry_mask.sum()
    )

    roads = roads.loc[~duplicate_geometry_mask].copy()

    roads = roads.to_crs(target_crs)

    roads["length_m"] = roads.geometry.length

    zero_length_mask = roads["length_m"] <= 0

    cleaning_statistics["removed_zero_length"] = int(
        zero_length_mask.sum()
    )

    roads = roads.loc[~zero_length_mask].copy()

    road_name_column = find_column(
        roads.columns,
        ROAD_NAME_CANDIDATES,
    )

    road_type_column = find_column(
        roads.columns,
        ROAD_TYPE_CANDIDATES,
    )

    if road_name_column:
        road_name = roads[road_name_column].astype("string")
    else:
        road_name = pd.Series(
            pd.NA,
            index=roads.index,
            dtype="string",
        )

    if road_type_column:
        road_type = roads[road_type_column].astype("string")
    else:
        road_type = pd.Series(
            "unclassified",
            index=roads.index,
            dtype="string",
        )

    cleaned_roads = gpd.GeoDataFrame(
        {
            "road_name": road_name,
            "road_type": road_type.fillna("unclassified"),
            "length_m": roads["length_m"].round(3),
            "cost": roads["length_m"].round(3),
            "reverse_cost": roads["length_m"].round(3),
            "geometry": roads.geometry,
        },
        geometry="geometry",
        crs=target_crs,
    )

    cleaned_roads = cleaned_roads.reset_index(drop=True)

    cleaned_roads.insert(
        0,
        "road_id",
        range(1, len(cleaned_roads) + 1),
    )

    cleaning_statistics["input_records"] = int(initial_count)
    cleaning_statistics["output_records"] = int(len(cleaned_roads))
    cleaning_statistics["invalid_after_repair"] = int(
        (~cleaned_roads.geometry.is_valid).sum()
    )

    return cleaned_roads, cleaning_statistics


def create_report(
    source_path: Path,
    target_crs: str,
    source_statistics: dict[str, Any],
    cleaning_statistics: dict[str, int],
    cleaned_roads: gpd.GeoDataFrame,
) -> dict[str, Any]:
    """Build the road data-quality report."""

    minimum_x, minimum_y, maximum_x, maximum_y = (
        cleaned_roads.total_bounds
    )

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "source_file": source_path.name,
        "target_crs": target_crs,
        "source": source_statistics,
        "cleaning": cleaning_statistics,
        "output": {
            "records": int(len(cleaned_roads)),
            "geometry_type": "LineString",
            "minimum_length_m": round(
                float(cleaned_roads["length_m"].min()),
                3,
            ),
            "maximum_length_m": round(
                float(cleaned_roads["length_m"].max()),
                3,
            ),
            "total_length_km": round(
                float(cleaned_roads["length_m"].sum()) / 1000,
                3,
            ),
            "bounding_box": {
                "minimum_x": round(float(minimum_x), 3),
                "minimum_y": round(float(minimum_y), 3),
                "maximum_x": round(float(maximum_x), 3),
                "maximum_y": round(float(maximum_y), 3),
            },
        },
    }


def write_report(
    report: dict[str, Any],
    report_path: Path,
) -> None:
    """Write the JSON report to disk."""

    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )


def print_summary(report: dict[str, Any]) -> None:
    """Display a concise processing summary."""

    source = report["source"]
    cleaning = report["cleaning"]
    output = report["output"]

    print("\nRoad data inspection")
    print("--------------------")
    print(f"Input CRS: {source['input_crs']}")
    print(f"Input records: {source['input_records']}")
    print(
        "Input geometry types: "
        f"{source['input_geometry_types']}"
    )

    print("\nRoad data cleaning")
    print("------------------")
    print(
        "Removed null or empty: "
        f"{cleaning['removed_null_or_empty']}"
    )
    print(
        "Invalid before repair: "
        f"{cleaning['invalid_before_repair']}"
    )
    print(
        "Removed non-line geometries: "
        f"{cleaning['removed_non_line_geometries']}"
    )
    print(
        "Removed duplicates: "
        f"{cleaning['removed_duplicate_geometries']}"
    )
    print(
        "Removed zero-length roads: "
        f"{cleaning['removed_zero_length']}"
    )

    print("\nCleaned road data")
    print("-----------------")
    print(f"Target CRS: {report['target_crs']}")
    print(f"Output records: {output['records']}")
    print(f"Total road length: {output['total_length_km']} km")


def load_into_postgis(
    roads: gpd.GeoDataFrame,
    engine: Engine,
    replace: bool,
) -> None:
    """Load the cleaned roads and create database indexes."""

    database_inspector = inspect(engine)

    table_exists = database_inspector.has_table(
        DATABASE_TABLE,
        schema=DATABASE_SCHEMA,
    )

    if table_exists and not replace:
        raise SystemExit(
            "routing.roads already exists. Run again with --replace "
            "only when you intentionally want to overwrite it."
        )

    if_exists = "replace" if replace else "fail"

    roads.to_postgis(
        name=DATABASE_TABLE,
        con=engine,
        schema=DATABASE_SCHEMA,
        if_exists=if_exists,
        index=False,
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                ALTER TABLE routing.roads
                ADD CONSTRAINT roads_pkey
                PRIMARY KEY (road_id);
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX roads_geometry_gix
                ON routing.roads
                USING GIST (geometry);
                """
            )
        )

        connection.execute(
            text(
                """
                ANALYZE routing.roads;
                """
            )
        )


def main() -> None:
    """Run the road-data ingestion pipeline."""

    arguments = parse_arguments()
    input_path = arguments.input.resolve()

    if not input_path.exists():
        raise SystemExit(
            f"Road dataset not found: {input_path}"
        )

    print(f"Reading road dataset: {input_path}")

    roads = gpd.read_file(input_path)

    if roads.empty:
        raise SystemExit("The road dataset contains no records.")

    source_statistics = inspect_source_data(roads)

    cleaned_roads, cleaning_statistics = clean_road_data(
        roads=roads,
        target_crs=arguments.target_crs,
    )

    if cleaned_roads.empty:
        raise SystemExit(
            "No usable LineString road geometries remain after cleaning."
        )

    report = create_report(
        source_path=input_path,
        target_crs=arguments.target_crs,
        source_statistics=source_statistics,
        cleaning_statistics=cleaning_statistics,
        cleaned_roads=cleaned_roads,
    )

    write_report(report, arguments.report)
    print_summary(report)

    print(f"\nReport saved to: {arguments.report}")

    if arguments.dry_run:
        print("\nDry run completed. Nothing was loaded into PostGIS.")
        return

    engine = create_database_engine()

    try:
        load_into_postgis(
            roads=cleaned_roads,
            engine=engine,
            replace=arguments.replace,
        )
    finally:
        engine.dispose()

    print(
        f"\nSuccessfully loaded {len(cleaned_roads)} roads "
        "into routing.roads."
    )


if __name__ == "__main__":
    main()