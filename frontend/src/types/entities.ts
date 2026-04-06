/**
 * Category A — moving entities streamed live via WebSocket.
 *
 * These types describe aircraft and ships. The server pushes updates to the
 * browser in real time; the Zustand store (entities.store.ts) applies them.
 *
 * Field names here must exactly match the JSON the Go API sends.
 */

/** Which data feed an entity came from. */
export type EntitySource = "adsb" | "ais" | "satellite";

/**
 * What kind of real-world object this is.
 *
 * "satellite" is used in Step 9 when the client-side Web Worker propagates
 * TLE positions and injects them directly into the Zustand entity store,
 * bypassing the server entirely.
 */
export type EntityType = "aircraft" | "ship" | "satellite";

/**
 * A single tracked moving entity — aircraft or ship.
 *
 * Optional fields (alt_m, heading_deg, etc.) may be absent when the
 * source feed didn't provide that information.
 */
export interface NormalizedEntity {
  /** Globally unique id: "{source}:{identifier}", e.g. "adsb:abc123" */
  id: string;
  source: EntitySource;
  entity_type: EntityType;
  lat: number;
  lon: number;
  /** Altitude in metres above sea level (aircraft only) */
  alt_m?: number;
  /** Direction of travel: 0 = North, increases clockwise */
  heading_deg?: number;
  /** Speed in nautical miles per hour */
  speed_knots?: number;
  /** Flight callsign or vessel name */
  callsign?: string;
  /** Source-specific extras: ICAO24, MMSI, country, etc. */
  metadata: Record<string, unknown>;
  /** ISO 8601 UTC timestamp when this position was recorded */
  timestamp: string;
}

/**
 * A message received from the WebSocket.
 *
 * Two variants:
 *  - type "update": entity position has changed — apply to the store
 *  - type "remove": entity has disappeared — delete from the store
 *  - type "snapshot": bulk initial state on first connect
 */
export type WsMessage =
  | { type: "update"; entity: NormalizedEntity }
  | { type: "remove"; id: string }
  | { type: "snapshot"; entities: NormalizedEntity[] };
