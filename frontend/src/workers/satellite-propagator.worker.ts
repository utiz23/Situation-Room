/**
 * satellite-propagator.worker.ts — Web Worker for computing satellite positions.
 *
 * A Web Worker is a background thread that runs JavaScript without blocking
 * the map UI. This is important because computing positions for thousands of
 * satellites involves real physics math that would make the map stutter if
 * run on the main thread.
 *
 * What this worker does:
 *   1. Fetch TLE data from /api/satellites/tles (once, on startup).
 *   2. Every 10 seconds, compute where each satellite is *right now* using
 *      the SGP4 orbital model (a physics formula for satellite orbits).
 *   3. Post the positions back to the main thread as a flat array.
 *
 * SGP4 stands for "Simplified General Perturbations model #4" — it's the
 * standard algorithm used by NORAD and everyone else to predict satellite
 * positions from TLE orbital elements.
 *
 * The satellite.js library wraps SGP4 in a friendly JavaScript API.
 *
 * Messages sent TO main thread:
 *   { type: 'positions', data: SatellitePosition[] }
 *   { type: 'status', status: string }   — informational (logged only)
 *   { type: 'error', message: string }   — fatal, worker will stop
 */

import * as satellite from 'satellite.js'
import type { TLERecord } from '../types/layers'

// ---------------------------------------------------------------------------
// Shared type for propagated satellite positions
// ---------------------------------------------------------------------------

export interface SatellitePosition {
  /** "satellite:{norad_cat_id}" — unique ID matching NormalizedEntity format */
  id: string
  /** Human-readable name, e.g. "STARLINK-1234" */
  name: string
  lat: number
  lon: number
  /** Altitude above Earth's surface, in metres */
  alt_m: number
}

// How often to recompute and post positions (ms)
const UPDATE_INTERVAL_MS = 10_000

// ---------------------------------------------------------------------------
// TLE fetch
// ---------------------------------------------------------------------------

async function fetchTLEs(): Promise<TLERecord[]> {
  const resp = await fetch('/api/satellites/tles')
  if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching TLEs`)
  return resp.json() as Promise<TLERecord[]>
}

// ---------------------------------------------------------------------------
// Position propagation
// ---------------------------------------------------------------------------

/**
 * Compute current positions for all satellites using the SGP4 model.
 *
 * For each TLE:
 *   1. Parse the two TLE lines into a "satrec" (satellite record) object.
 *   2. Call propagate(satrec, now) → position in ECI coordinates.
 *      ECI = "Earth-Centred Inertial" — a 3D coordinate system fixed to space,
 *      not rotating with the Earth.
 *   3. Convert ECI to geodetic (lat/lon/alt) using the current GMST angle.
 *      GMST = "Greenwich Mean Sidereal Time" — how far the Earth has rotated.
 *
 * Satellites with bad TLEs (decayed, stale epoch) will have NaN or false
 * positions — we skip those silently.
 */
function propagateAll(tles: TLERecord[]): SatellitePosition[] {
  const now  = new Date()
  const gmst = satellite.gstime(now)
  const positions: SatellitePosition[] = []

  for (const tle of tles) {
    try {
      const satrec = satellite.twoline2satrec(tle.tle_line1, tle.tle_line2)
      const result = satellite.propagate(satrec, now)

      // propagate() returns false for position/velocity when the satellite
      // has decayed or the TLE epoch is too far from now.
      if (!result.position || typeof result.position === 'boolean') continue

      const geo = satellite.eciToGeodetic(result.position, gmst)
      const lat = satellite.degreesLat(geo.latitude)
      const lon = satellite.degreesLong(geo.longitude)
      // satellite.js returns height in kilometres; convert to metres
      const alt_m = geo.height * 1000

      // Sanity-check: skip positions that resolved to NaN or infinity
      if (!isFinite(lat) || !isFinite(lon) || !isFinite(alt_m)) continue

      positions.push({
        id: `satellite:${tle.norad_cat_id}`,
        name: tle.name,
        lat,
        lon,
        alt_m,
      })
    } catch {
      // Silently skip satellites that fail SGP4 propagation
    }
  }

  return positions
}

// ---------------------------------------------------------------------------
// Main worker loop
// ---------------------------------------------------------------------------

async function main(): Promise<void> {
  // Step 1: fetch TLEs from the API
  let tles: TLERecord[]
  try {
    tles = await fetchTLEs()
    postMessage({ type: 'status', status: `loaded ${tles.length} TLEs` })
  } catch (err) {
    postMessage({ type: 'error', message: String(err) })
    return  // can't continue without TLEs
  }

  // Step 2: propagate immediately on load so the layer appears right away
  const tick = (): void => {
    const data = propagateAll(tles)
    postMessage({ type: 'positions', data })
  }

  tick()
  setInterval(tick, UPDATE_INTERVAL_MS)
}

main()
