"""Verify the PostgreSQL, PostGIS, and pgRouting configuration."""

from __future__ import annotations

import os
from typing import Final

import psycopg
from dotenv import load_dotenv


REQUIRED_ENVIRONMENT_VARIABLES: Final[tuple[str, ...]] = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
)


def get_required_environment_variable(name: str) -> str:
    """Return a required environment variable or stop with a clear error."""

    value = os.getenv(name)

    if not value:
        raise SystemExit(
            f"Missing environment variable: {name}. "
            "Check the local .env file."
        )

    return value


def main() -> None:
    """Connect to PostgreSQL and verify the spatial extensions."""

    load_dotenv()

    settings = {
        name: get_required_environment_variable(name)
        for name in REQUIRED_ENVIRONMENT_VARIABLES
    }

    try:
        with psycopg.connect(
            host=settings["DB_HOST"],
            port=settings["DB_PORT"],
            dbname=settings["DB_NAME"],
            user=settings["DB_USER"],
            password=settings["DB_PASSWORD"],
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        current_database(),
                        current_user,
                        current_setting('search_path');
                    """
                )
                database_name, database_user, search_path = cursor.fetchone()

                cursor.execute(
                    """
                    SELECT
                        extname,
                        extversion
                    FROM pg_extension
                    WHERE extname IN ('postgis', 'pgrouting')
                    ORDER BY extname;
                    """
                )
                extensions = cursor.fetchall()

    except psycopg.Error as error:
        raise SystemExit(
            f"Database connection or validation failed: {error}"
        ) from error

    installed_extensions = {
        extension_name: extension_version
        for extension_name, extension_version in extensions
    }

    print("Database connection successful.\n")
    print(f"Database: {database_name}")
    print(f"User: {database_user}")
    print(f"Search path: {search_path}\n")

    missing_extensions = []

    for extension_name in ("postgis", "pgrouting"):
        version = installed_extensions.get(extension_name)

        if version:
            print(f"[OK] {extension_name} {version}")
        else:
            print(f"[FAILED] {extension_name} is not installed")
            missing_extensions.append(extension_name)

    if missing_extensions:
        raise SystemExit(
            "Database validation failed. Missing extensions: "
            + ", ".join(missing_extensions)
        )

    print("\nSpatial database check completed successfully.")


if __name__ == "__main__":
    main()