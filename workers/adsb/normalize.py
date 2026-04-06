"""
OpenSky state vector → NormalizedEntity converter.

OpenSky returns aircraft positions as a list of 17 unnamed values (a "state
vector"). Think of it like a spreadsheet row with no column headers — you have
to know which position means what.

Field index reference (from OpenSky docs):
  0  icao24          Unique hex identifier for the aircraft transponder
  1  callsign        Flight number / tail number (may have trailing spaces)
  2  origin_country  Country of registration
  3  time_position   Unix timestamp of the last position update
  4  last_contact    Unix timestamp of the last ANY update
  5  longitude       Decimal degrees (WGS84)
  6  latitude        Decimal degrees (WGS84)
  7  baro_altitude   Barometric altitude in metres (can be None if on ground)
  8  on_ground       True if the aircraft is reporting as on the ground
  9  velocity        Ground speed in metres/second
  10 true_track      Track angle (heading) in degrees, clockwise from North
  11 vertical_rate   Rate of climb/descent in metres/second
  12 sensors         (internal use, ignore)
  13 geo_altitude    GPS altitude in metres
  14 squawk          Transponder squawk code (4-digit octal, ignore for now)
  15 spi             Special purpose indicator (ignore)
  16 position_source 0=ADS-B, 1=ASTERIX, 2=MLAT, 3=FLARM

We skip rows where lat or lon is missing — no position means nothing to show.
"""

from datetime import datetime, timezone
from typing import Optional

from common.schema import NormalizedEntity

# Conversion factor: 1 metre/second = 1.94384 nautical miles/hour (knots)
_MS_TO_KNOTS = 1.94384


def normalize(state_vector: list) -> Optional[NormalizedEntity]:
    """
    Convert one OpenSky state vector into a NormalizedEntity.

    Returns None if the row is missing lat/lon (can't place it on the map).
    """
    icao24: str = state_vector[0]
    callsign: Optional[str] = state_vector[1]
    origin_country: str = state_vector[2]
    time_position: Optional[int] = state_vector[3]
    last_contact: int = state_vector[4]
    lon: Optional[float] = state_vector[5]
    lat: Optional[float] = state_vector[6]
    baro_altitude: Optional[float] = state_vector[7]
    on_ground: bool = state_vector[8]
    velocity_ms: Optional[float] = state_vector[9]
    true_track: Optional[float] = state_vector[10]
    geo_altitude: Optional[float] = state_vector[13]
    squawk: Optional[str] = state_vector[14]

    # Can't render without a position
    if lat is None or lon is None:
        return None

    # Use the position timestamp if available, otherwise fall back to last_contact
    ts_unix = time_position if time_position is not None else last_contact
    timestamp = datetime.fromtimestamp(ts_unix, tz=timezone.utc)

    # Prefer GPS altitude; fall back to barometric; fall back to None
    alt_m = geo_altitude if geo_altitude is not None else baro_altitude

    # Convert speed from m/s to knots
    speed_knots = velocity_ms * _MS_TO_KNOTS if velocity_ms is not None else None

    # Strip trailing whitespace OpenSky often includes in callsigns
    clean_callsign = callsign.strip() if callsign and callsign.strip() else None

    return NormalizedEntity(
        id=f"adsb:{icao24}",
        source="adsb",
        entity_type="aircraft",
        lat=lat,
        lon=lon,
        alt_m=alt_m,
        heading_deg=true_track,
        speed_knots=speed_knots,
        callsign=clean_callsign,
        metadata={
            "icao24": icao24,
            "origin_country": origin_country,
            "on_ground": on_ground,
            "squawk": squawk,
        },
        timestamp=timestamp,
    )
