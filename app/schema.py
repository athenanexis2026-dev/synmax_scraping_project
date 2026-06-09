"""SQLite schema for the SynMax database."""

ASSIGNMENT_COLUMNS = [
    "Operator",
    "Status",
    "Well Type",
    "Work Type",
    "Directional Status",
    "Multi-Lateral",
    "Mineral Owner",
    "Surface Owner",
    "Surface Location",
    "GL Elevation",
    "KB Elevation",
    "DF Elevation",
    "Single/Multiple Completion",
    "Potash Waiver",
    "Spud Date",
    "Last Inspection",
    "TVD",
    "API",
    "Latitude",
    "Longitude",
    "CRS",
]

INTEGER_COLUMNS = {"GL Elevation", "KB Elevation", "DF Elevation", "TVD"}
REAL_COLUMNS = {"Latitude", "Longitude"}


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_well_data (
    "Operator" TEXT,
    "Status" TEXT,
    "Well Type" TEXT,
    "Work Type" TEXT,
    "Directional Status" TEXT,
    "Multi-Lateral" TEXT,
    "Mineral Owner" TEXT,
    "Surface Owner" TEXT,
    "Surface Location" TEXT,
    "GL Elevation" INTEGER,
    "KB Elevation" INTEGER,
    "DF Elevation" INTEGER,
    "Single/Multiple Completion" TEXT,
    "Potash Waiver" TEXT,
    "Spud Date" TEXT,
    "Last Inspection" TEXT,
    "TVD" INTEGER,
    "API" TEXT PRIMARY KEY NOT NULL,
    "Latitude" REAL,
    "Longitude" REAL,
    "CRS" TEXT
);
"""

GEO_COORDINATE_COLUMNS = """
CREATE INDEX IF NOT EXISTS idx_api_well_data_lat_lon
    ON api_well_data ("Latitude", "Longitude");
"""
