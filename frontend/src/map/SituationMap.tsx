/**
 * SituationMap — the root map component.
 *
 * Renders a full-screen interactive globe using:
 *   - MapLibre GL JS for the basemap (via react-map-gl)
 *   - Deck.gl for GPU-accelerated entity layers on top
 *
 * On every map move, the current viewport bounding box is sent to the server
 * via WebSocket so the Go hub can filter which entity updates to forward.
 * This is the "viewport filtering" feature described in the architecture.
 */

import { useCallback, useRef, useState } from 'react'
import DeckGL from '@deck.gl/react'
import { WebMercatorViewport } from '@deck.gl/core'
import type { MapViewState } from '@deck.gl/core'
import Map from 'react-map-gl/maplibre'
import 'maplibre-gl/dist/maplibre-gl.css'

import { useEntityStream } from '../hooks/useEntityStream'
import { useAircraftLayer } from './layers/AircraftLayer'
import { useShipLayer } from './layers/ShipLayer'
import { useGpsJamLayer } from './layers/GpsJamLayer'
import { useSatelliteLayer } from './layers/SatelliteLayer'
import { useEventLayer } from './layers/EventLayer'

// OpenFreeMap liberty style — free, no API key required.
// Serves vector tiles and renders them client-side with MapLibre.
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

// Starting view: centred over Europe/North Atlantic (matches the default ADSB_BBOX).
const INITIAL_VIEW_STATE: MapViewState = {
  longitude: 10,
  latitude:  48,
  zoom:      4,
  pitch:     0,
  bearing:   0,
}

/**
 * Compute the geographic bounding box of the current viewport.
 * Returns [minLat, minLon, maxLat, maxLon] — the format the Go hub expects.
 */
function viewStateToBBox(
  viewState: MapViewState,
  width: number,
  height: number,
): [number, number, number, number] {
  const vp = new WebMercatorViewport({ ...viewState, width, height })
  const [west, south] = vp.unproject([0, height])
  const [east, north] = vp.unproject([width, 0])
  return [south, west, north, east]
}

export default function SituationMap() {
  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW_STATE)

  const { sendViewport } = useEntityStream()
  const gpsJamLayer   = useGpsJamLayer()
  const eventLayer    = useEventLayer()
  const shipLayer     = useShipLayer()
  const satelliteLayer = useSatelliteLayer()
  const aircraftLayer = useAircraftLayer()

  // Layer order = render order (bottom → top):
  //   GPS jam hexes → events → ships → satellites → aircraft
  const layers = [gpsJamLayer, eventLayer, shipLayer, satelliteLayer, aircraftLayer].filter(Boolean)

  // Debounce viewport messages: onViewStateChange fires at up to 60 fps during
  // drag/zoom. We only need to tell the server when the camera settles, so we
  // wait 150 ms after the last event before sending. This keeps WS traffic low
  // without meaningfully delaying the hub's viewport filter update.
  const vpTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleViewStateChange = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ({ viewState: next }: { viewState: any }) => {
      setViewState(next as MapViewState)

      if (vpTimerRef.current) clearTimeout(vpTimerRef.current)
      vpTimerRef.current = setTimeout(() => {
        const bbox = viewStateToBBox(next, window.innerWidth, window.innerHeight)
        sendViewport(bbox)
      }, 150)
    },
    [sendViewport],
  )

  return (
    <DeckGL
      viewState={viewState}
      onViewStateChange={handleViewStateChange}
      controller={true}
      layers={layers}
    >
      {/* Map renders as a child of DeckGL so they share the same WebGL context */}
      <Map mapStyle={MAP_STYLE} />
    </DeckGL>
  )
}
