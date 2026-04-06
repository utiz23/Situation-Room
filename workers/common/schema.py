"""
Shared data schemas for all SituationRoom workers.

Think of these as "blueprints" — they define exactly what fields each piece of
data must have. Pydantic (the library used here) validates the data automatically:
if a required field is missing or the wrong type, it raises an error immediately
so bugs are caught early rather than silently corrupting the database.

Two categories of data:
  Category A — moving entities streamed live (aircraft, ships)
  Category B — static/derived layers fetched on demand (events, jamming, TLEs)
"""

from __future__ import annotations

from datetime import datetime, date as DateType
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Category A — NormalizedEntity
# ---------------------------------------------------------------------------
# Every moving thing on the map (aircraft, ship) is normalized into this shape
# before being published to Redis and inserted into entity_positions.
#
# The "id" field follows the pattern "{source}:{identifier}", e.g.:
#   "adsb:abc123"   — an aircraft identified by its ICAO24 hex code
#   "ais:987654321" — a ship identified by its MMSI number

class NormalizedEntity(BaseModel):
    id: str = Field(
        description='Globally unique entity id in the form "{source}:{identifier}"'
    )
    source: Literal["adsb", "ais", "satellite"] = Field(
        description="Which data feed this came from"
    )
    entity_type: Literal["aircraft", "ship", "satellite"] = Field(
        description=(
            "What kind of real-world object this is. "
            "'satellite' is used in Step 9 when the client-side Web Worker "
            "propagates TLE positions and injects them directly into the "
            "Zustand store — the Python workers never produce satellite entities."
        )
    )
    lat: float = Field(description="Latitude in decimal degrees (-90 to 90)")
    lon: float = Field(description="Longitude in decimal degrees (-180 to 180)")
    alt_m: Optional[float] = Field(
        default=None, description="Altitude in metres above sea level (aircraft only)"
    )
    heading_deg: Optional[float] = Field(
        default=None, description="Direction of travel in degrees (0 = North, clockwise)"
    )
    speed_knots: Optional[float] = Field(
        default=None, description="Speed in nautical miles per hour"
    )
    callsign: Optional[str] = Field(
        default=None,
        description="Flight number (aircraft) or vessel name (ship)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific extras, e.g. {'icao24': 'abc123', 'country': 'US'}"
    )
    timestamp: datetime = Field(
        description="UTC time when this position was recorded"
    )


# ---------------------------------------------------------------------------
# Category B — Event
# ---------------------------------------------------------------------------
# A manually pinned incident on the map: strike, explosion, military movement, etc.
# Created by an admin via POST /api/events.

class Event(BaseModel):
    id: Optional[UUID] = Field(
        default=None,
        description="Database UUID — None before the row is inserted"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="When this event was added to the system (set by DB)"
    )
    event_time: datetime = Field(
        description="When the real-world incident occurred (UTC)"
    )
    lat: float = Field(description="Latitude where the event happened")
    lon: float = Field(description="Longitude where the event happened")
    event_type: str = Field(
        description="Category: 'strike' | 'explosion' | 'military_movement' | 'protest' | 'other'"
    )
    title: str = Field(description="Short description, e.g. 'Missile strike on fuel depot'")
    description: Optional[str] = Field(default=None, description="Longer details")
    source_url: Optional[str] = Field(
        default=None, description="Link to a news article or source"
    )
    verified: bool = Field(
        default=False, description="True if an admin has confirmed this event"
    )
    contributor: Optional[str] = Field(
        default=None, description="Who submitted it (for attribution)"
    )


# ---------------------------------------------------------------------------
# Category B — JammingHex
# ---------------------------------------------------------------------------
# One row in the GPSJam daily dataset.
# Each hex represents a geographic hexagon (H3 format) and the percentage of
# aircraft over it that reported GPS interference.

class JammingHex(BaseModel):
    h3_index: str = Field(
        description="H3 hexagon identifier, e.g. '8928308280fffff'"
    )
    interference_pct: float = Field(
        description="0.0–100.0: percentage of flights reporting GPS issues in this hex"
    )
    date: DateType = Field(description="The calendar day this reading covers")


# ---------------------------------------------------------------------------
# Category B — TLERecord
# ---------------------------------------------------------------------------
# One satellite's Two-Line Element set, fetched from CelesTrak.
# The frontend uses these to compute satellite positions client-side.

class TLERecord(BaseModel):
    norad_cat_id: int = Field(
        description="NORAD catalog number — the universal unique ID for every satellite"
    )
    name: str = Field(description="Human-readable name, e.g. 'STARLINK-1234'")
    tle_line1: str = Field(description="First line of the TLE data string")
    tle_line2: str = Field(description="Second line of the TLE data string")
    constellation: str = Field(
        description="Group: 'starlink' | 'iridium-next' | 'active' | etc."
    )
    fetched_at: Optional[datetime] = Field(
        default=None,
        description="When we last retrieved this TLE from CelesTrak (set by DB)"
    )
