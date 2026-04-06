/**
 * AircraftLayer — renders live aircraft positions on the map.
 *
 * Currently uses ScatterplotLayer (coloured dots) for simplicity.
 * Step 12 (UI polish) will upgrade this to IconLayer with a directional
 * aircraft icon that rotates to match heading_deg.
 *
 * Returns null when the aircraft layer is toggled off in the UI store.
 */

import { useMemo } from 'react'
import { ScatterplotLayer } from '@deck.gl/layers'
import { useEntitiesStore } from '../../store/entities.store'
import { useUiStore } from '../../store/ui.store'
import type { NormalizedEntity } from '../../types/entities'

// Cyan — stands out against the dark map basemap and ocean
const AIRCRAFT_COLOR: [number, number, number, number] = [0, 210, 255, 220]

export function useAircraftLayer() {
  const visible  = useUiStore((s) => s.layers.aircraft)
  const entities = useEntitiesStore((s) => s.entities)

  // Derive the aircraft array only when the entities Map reference changes.
  const aircraft = useMemo(
    () =>
      visible
        ? ([...entities.values()].filter((e) => e.entity_type === 'aircraft') as NormalizedEntity[])
        : [],
    [entities, visible],
  )

  return useMemo(
    () =>
      new ScatterplotLayer<NormalizedEntity>({
        id: 'aircraft',
        data: aircraft,
        getPosition: (e) => [e.lon, e.lat, e.alt_m ?? 0],
        getFillColor: AIRCRAFT_COLOR,
        getRadius: 4_000, // 4 km — visible at zoom 4, not overwhelming at zoom 8
        radiusMinPixels: 3,
        radiusMaxPixels: 14,
        pickable: true,
        // updateTriggers tells deck.gl exactly which props changed so it avoids
        // re-uploading unchanged GPU buffers on every render.
        updateTriggers: {
          getPosition: aircraft,
          getFillColor: aircraft,
        },
      }),
    [aircraft],
  )
}
