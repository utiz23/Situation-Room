/**
 * SatelliteLayer — renders live satellite positions on the map.
 *
 * Architecture (all client-side, server never computes positions):
 *
 *   1. When the satellite toggle is switched ON, we start a Web Worker
 *      (satellite-propagator.worker.ts) in the background.
 *   2. The worker fetches TLEs from /api/satellites/tles, then every 10s
 *      uses satellite.js SGP4 physics to compute current positions and
 *      posts them back here as a flat array.
 *   3. We store those positions in React state and render them as a
 *      Deck.gl ScatterplotLayer (tiny colored dots on the globe).
 *   4. When the toggle is switched OFF, we terminate the worker to free
 *      resources and clear the dots from the map.
 *
 * The Web Worker runs on a separate CPU thread so the satellite math
 * never blocks the 60fps map rendering loop.
 */

import { useEffect, useRef, useState } from 'react'
import { ScatterplotLayer } from '@deck.gl/layers'
import type { Layer } from '@deck.gl/core'
import { useUiStore } from '../../store/ui.store'
import type { SatellitePosition } from '../../workers/satellite-propagator.worker'

export function useSatelliteLayer(): Layer | null {
  const visible = useUiStore((s) => s.layers.satellites)

  const [positions, setPositions] = useState<SatellitePosition[]>([])
  const workerRef = useRef<Worker | null>(null)

  useEffect(() => {
    if (!visible) {
      // Layer toggled off — terminate the worker and clear dots
      if (workerRef.current) {
        workerRef.current.terminate()
        workerRef.current = null
        setPositions([])
      }
      return
    }

    // Layer toggled on — start the worker
    // Vite handles the ?worker-style URL so this chunk is split automatically.
    const worker = new Worker(
      new URL('../../workers/satellite-propagator.worker.ts', import.meta.url),
      { type: 'module' },
    )

    worker.onmessage = (e: MessageEvent) => {
      if (e.data.type === 'positions') {
        setPositions(e.data.data as SatellitePosition[])
      } else if (e.data.type === 'error') {
        console.error('[satellite-worker]', e.data.message)
      }
    }

    worker.onerror = (err: ErrorEvent) => {
      console.error('[satellite-worker] uncaught error:', err.message)
    }

    workerRef.current = worker

    // Clean up the worker when the component unmounts or visible changes again
    return () => {
      worker.terminate()
      workerRef.current = null
    }
  }, [visible])

  if (!visible || positions.length === 0) return null

  return new ScatterplotLayer<SatellitePosition>({
    id: 'satellites',
    data: positions,
    // Deck.gl expects [longitude, latitude] (note: lon before lat)
    getPosition: (d) => [d.lon, d.lat],
    // Gold/yellow dots to distinguish satellites from aircraft (white) and ships (blue)
    getFillColor: [255, 220, 50, 200],
    getRadius: 3,
    radiusMinPixels: 2,
    radiusMaxPixels: 6,
    pickable: true,
  })
}
