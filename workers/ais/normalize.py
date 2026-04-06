"""
AISStream message → NormalizedEntity converter.

AISStream sends decoded AIS (Automatic Identification System) messages over
WebSocket. AIS is the radio protocol that ships use to broadcast their position,
speed, and identity to nearby vessels and coast stations.

The message we care about is "PositionReport" (AIS message types 1, 2, 3).
It contains the ship's current lat/lon, speed, and heading.

AISStream message shape:
  {
    "MessageType": "PositionReport",
    "MetaData": {
      "MMSI": 123456789,       -- unique ship ID (like an aircraft's ICAO24)
      "ShipName": "MY VESSEL",
      "latitude": 51.5,        -- position at time of message
      "longitude": -0.1,
      "time_utc": "2024-01-01 12:00:00"
    },
    "Message": {
      "PositionReport": {
        "Sog": 5.2,            -- Speed Over Ground in knots (already knots, no conversion)
        "TrueHeading": 270,    -- 511 means "not available"
        "Cog": 269.8,          -- Course Over Ground (fallback when TrueHeading unavailable)
        "NavigationalStatus": 0, -- 0=underway, 1=anchored, 5=moored, etc.
        "RateOfTurn": 0.0,
        "UserID": 123456789    -- same as MMSI
      }
    }
  }

Key AIS quirks:
  - TrueHeading == 511 means the ship's compass is not reporting (use Cog instead)
  - Lat/lon (0.0, 0.0) is the AIS "not available" sentinel — we skip these
  - Ships only broadcast every 2–10 seconds when moving; silent ships age out
    via client-side TTL (10 min) rather than an explicit "remove" signal
"""

from datetime import datetime, timezone
from typing import Optional

from common.schema import NormalizedEntity

# AIS uses 511 as a sentinel meaning "true heading not available"
_HEADING_NOT_AVAILABLE = 511


def normalize(message: dict) -> Optional[NormalizedEntity]:
    """
    Convert one AISStream message into a NormalizedEntity.

    Returns None if the message is not a PositionReport, has no position,
    or has the AIS null-island sentinel position (0.0, 0.0).
    """
    if message.get("MessageType") != "PositionReport":
        return None

    meta   = message.get("MetaData", {})
    report = message.get("Message", {}).get("PositionReport", {})

    mmsi: Optional[int] = meta.get("MMSI") or report.get("UserID")
    if not mmsi:
        return None

    # MetaData carries pre-decoded lat/lon; fall back to the raw report fields
    lat: Optional[float] = meta.get("latitude") or report.get("Latitude")
    lon: Optional[float] = meta.get("longitude") or report.get("Longitude")

    if lat is None or lon is None:
        return None

    # AIS uses (0.0, 0.0) as "position not available" — skip null island
    if lat == 0.0 and lon == 0.0:
        return None

    # Speed Over Ground — AIS already transmits in knots, no conversion needed
    sog: Optional[float] = report.get("Sog")

    # Prefer TrueHeading; fall back to Course Over Ground (Cog) if not available
    true_heading: Optional[int] = report.get("TrueHeading")
    cog: Optional[float]        = report.get("Cog")
    heading: Optional[float]    = (
        float(true_heading)
        if (true_heading is not None and true_heading != _HEADING_NOT_AVAILABLE)
        else cog
    )

    # Ship name comes from MetaData; strip whitespace AIS often pads with spaces
    ship_name_raw = meta.get("ShipName", "")
    ship_name     = ship_name_raw.strip() or None

    # Parse the UTC timestamp from MetaData; fall back to "now" if missing/invalid
    time_utc_str: Optional[str] = meta.get("time_utc")
    try:
        timestamp = (
            datetime.strptime(time_utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if time_utc_str
            else datetime.now(timezone.utc)
        )
    except ValueError:
        timestamp = datetime.now(timezone.utc)

    return NormalizedEntity(
        id=f"ais:{mmsi}",
        source="ais",
        entity_type="ship",
        lat=lat,
        lon=lon,
        heading_deg=heading,
        speed_knots=sog if sog is not None and sog < 102.2 else None,  # 102.2+ = not available
        callsign=ship_name,
        metadata={
            "mmsi":            mmsi,
            "nav_status":      report.get("NavigationalStatus"),
            "rate_of_turn":    report.get("RateOfTurn"),
        },
        timestamp=timestamp,
    )
