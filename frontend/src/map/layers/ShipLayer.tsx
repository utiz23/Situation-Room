/**
 * ShipLayer — renders live AIS ship positions on the map.
 *
 * Uses ScatterplotLayer (coloured dots). Step 12 (UI polish) can upgrade
 * this to an IconLayer with a vessel silhouette rotated to match heading_deg.
 *
 * Ships use a distinct orange colour so they're visually separate from
 * the cyan aircraft dots.
 *
 * Returns an empty layer (no dots) when the ships toggle is off in the UI store.
 */

import { useMemo } from 'react'
import { ScatterplotLayer } from '@deck.gl/layers'
import type { PickingInfo } from '@deck.gl/core'
import { useEntitiesStore } from '../../store/entities.store'
import { useUiStore } from '../../store/ui.store'
import type { NormalizedEntity } from '../../types/entities'

// Orange — visually distinct from aircraft (cyan) and the basemap
const SHIP_COLOR: [number, number, number, number] = [255, 160, 0, 220]

interface Props {
  onPick?: (info: PickingInfo) => void
}

export function useShipLayer({ onPick }: Props = {}) {
  const visible  = useUiStore((s) => s.layers.ships)
  const entities = useEntitiesStore((s) => s.entities)

  const ships = useMemo(
    () =>
      visible
        ? ([...entities.values()].filter((e) => e.entity_type === 'ship') as NormalizedEntity[])
        : [],
    [entities, visible],
  )

  return useMemo(
    () =>
      new ScatterplotLayer<NormalizedEntity>({
        id: 'ships',
        data: ships,
        getPosition: (e) => [e.lon, e.lat, 0],
        getFillColor: SHIP_COLOR,
        getRadius: 5_000,
        radiusMinPixels: 3,
        radiusMaxPixels: 16,
        pickable: true,
        onClick: onPick,
        updateTriggers: {
          getPosition: ships,
          getFillColor: ships,
        },
      }),
    [ships, onPick],
  )
}
