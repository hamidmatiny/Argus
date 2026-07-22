"""Load Iceberg catalogs: REST (local), Glue (prod), or SqlCatalog (tests)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pyiceberg.catalog import Catalog, load_catalog
from pyiceberg.exceptions import NamespaceAlreadyExistsError, TableAlreadyExistsError
from pyiceberg.partitioning import PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.table import Table

from common.config import (
    CATALOG_NAME,
    CATALOG_TYPE,
    CATALOG_URI,
    GLUE_DATABASE,
    GLUE_REGION,
    NAMESPACE,
    PARQUET_COMPRESSION,
    S3_ACCESS_KEY,
    S3_ENDPOINT,
    S3_PATH_STYLE,
    S3_REGION,
    S3_SECRET_KEY,
    WAREHOUSE,
)

logger = logging.getLogger("argus.lakehouse.catalog")


def _s3_props() -> dict[str, str]:
    props = {
        "s3.endpoint": S3_ENDPOINT,
        "s3.access-key-id": S3_ACCESS_KEY,
        "s3.secret-access-key": S3_SECRET_KEY,
        "s3.region": S3_REGION,
        "s3.path-style-access": "true" if S3_PATH_STYLE else "false",
        # PyIceberg / PyArrow FileIO
        "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
    }
    return props


def load_iceberg_catalog(
    *,
    catalog_type: str | None = None,
    uri: str | None = None,
    warehouse: str | None = None,
    sqlite_path: str | Path | None = None,
) -> Catalog:
    """
    Load a catalog.

    - rest: Iceberg REST (docker-compose / local)
    - glue: AWS Glue (prod; hydra-data-factory continuity)
    - sqlite: file-backed SqlCatalog for unit tests
    """
    kind = (catalog_type or CATALOG_TYPE).lower()
    wh = warehouse or WAREHOUSE

    if kind in {"sqlite", "sql"}:
        if sqlite_path is None:
            raise ValueError("sqlite_path is required for catalog_type=sqlite")
        path = Path(sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return load_catalog(
            CATALOG_NAME,
            **{
                "type": "sql",
                "uri": f"sqlite:///{path}",
                "warehouse": wh,
            },
        )

    if kind == "glue":
        return load_catalog(
            CATALOG_NAME,
            **{
                "type": "glue",
                "warehouse": wh,
                "client.region": GLUE_REGION,
                **_s3_props(),
            },
        )

    # Default: REST
    return load_catalog(
        CATALOG_NAME,
        **{
            "type": "rest",
            "uri": uri or CATALOG_URI,
            "warehouse": wh,
            **_s3_props(),
        },
    )


def ensure_namespace(catalog: Catalog, namespace: str = NAMESPACE) -> None:
    try:
        catalog.create_namespace(namespace)
        logger.info("namespace_created", extra={"namespace": namespace})
    except NamespaceAlreadyExistsError:
        pass
    # Glue databases may already exist under a different API.
    except Exception as exc:  # noqa: BLE001
        if "AlreadyExists" in type(exc).__name__ or "already exists" in str(exc).lower():
            return
        # Some catalogs use create_namespace((name,))
        try:
            catalog.create_namespace((namespace,))
        except Exception:
            logger.debug("namespace_ensure_skipped", extra={"error": str(exc)})


def ensure_table(
    catalog: Catalog,
    *,
    namespace: str,
    table_name: str,
    schema: Schema,
    partition_spec: PartitionSpec,
    properties: dict[str, str] | None = None,
) -> Table:
    """Create the Iceberg table if missing; return a loaded handle."""
    ensure_namespace(catalog, namespace)
    ident = f"{namespace}.{table_name}"
    props = {
        "write.format.default": "parquet",
        "write.parquet.compression-codec": PARQUET_COMPRESSION,
        **(properties or {}),
    }
    try:
        table = catalog.create_table(
            ident,
            schema=schema,
            partition_spec=partition_spec,
            properties=props,
        )
        logger.info("table_created", extra={"table": ident})
        return table
    except TableAlreadyExistsError:
        return catalog.load_table(ident)
    except Exception as exc:  # noqa: BLE001
        if "AlreadyExists" in type(exc).__name__ or "already exists" in str(exc).lower():
            return catalog.load_table(ident)
        raise


def table_identifier(namespace: str, table_name: str) -> str:
    return f"{namespace}.{table_name}"


def glue_note() -> dict[str, Any]:
    """Document prod Glue wiring (no network call)."""
    return {
        "catalog_type": "glue",
        "database": GLUE_DATABASE,
        "region": GLUE_REGION,
        "warehouse": WAREHOUSE,
        "continuity": "hydra-data-factory Glue database/table pattern",
    }
