/**
 * GpsJamLayer — renders GPS interference hexagons from GPSJam.org.
 *
 * Uses deck.gl's H3HexagonLayer, which understands H3 hex indexes natively.
 * H3 is a geographic hexagonal grid — each cell covers ~85 km² at resolution 5.
 *
 * Bundle-size note:
 *   @deck.gl/geo-layers + h3-js together are ~1 MB. We only import them when
 *   the GPS Jam layer is toggled ON for the first time, using a dynamic import
 *   inside a useEffect. Until then, the chunk is not downloaded.
 *
 * Color scale:
 *   Low interference (0%)  → transparent green
 *   High interference (100%) → opaque red
 *
 * Returns null (no layer) when the gpsJam toggle is off in the UI store.
 */

import { useEffect, useMemo, useState } from 'react'
import type { Layer } from '@deck.gl/core'
import { useUiStore } from '../../store/ui.store'
import type { JammingHex } from '../../types/layers'

// H3HexagonLayer type — imported lazily so the module loads only when needed
type H3HexagonLayerType = new (props: Record<string, unknown>) => Layer

function interferenceToColor(pct: number): [number, number, number, number] {
  // Map 0–100% → green → yellow → red, with opacity increasing with severity
  const t = Math.min(pct / 100, 1)
  return [
    Math.round(255 * t),           // R: 0 at 0%, 255 at 100%
    Math.round(255 * (1 - t)),     // G: 255 at 0%, 0 at 100%
    0,
    Math.round(80 + 150 * t),     // A: semi-transparent at low%, opaque at high%
  ]
}

export function useGpsJamLayer(): Layer | null {
  const visible = useUiStore((s) => s.layers.gpsJam)

  const [hexes, setHexes]           = useState<JammingHex[]>([])
  const [LayerClass, setLayerClass] = useState<H3HexagonLayerType | null>(null)
  const [loading, setLoading]       = useState(false)

  // Lazy-load @deck.gl/geo-layers + fetch data on first enable
  useEffect(() => {
    if (!visible || LayerClass) return  // already loaded or layer is off

    setLoading(true)

    Promise.all([
      // Dynamic import: Vite/webpack splits this into its own chunk (~1 MB)
      import('@deck.gl/geo-layers').then((m) => m.H3HexagonLayer as unknown as H3HexagonLayerType),
      fetch('/api/gpsjam/current').then((r) => r.json() as Promise<JammingHex[]>),
    ])
      .then(([Cls, data]) => {
        setLayerClass(() => Cls)
        setHexes(data)
      })
      .catch((err) => {
        console.error('[gpsjam] failed to load layer or data:', err)
      })
      .finally(() => setLoading(false))
  }, [visible, LayerClass])

  return useMemo(() => {
    if (!visible || !LayerClass || hexes.length === 0) return null

    if (loading) return null  // still fetching — return nothing rather than a stale layer

    return new LayerClass({
      id:          'gpsjam',
      data:        hexes,
      getHexagon:  (d: JammingHex) => d.h3_index,
      getFillColor: (d: JammingHex) => interferenceToColor(d.interference_pct),
      extruded:    false,
      pickable:    true,
      updateTriggers: { getFillColor: hexes },
    }) as unknown as Layer
  }, [visible, LayerClass, hexes, loading])
}
