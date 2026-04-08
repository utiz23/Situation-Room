/**
 * AircraftLayer — renders live aircraft as directional icons.
 *
 * Uses deck.gl IconLayer so each aircraft icon can rotate to match its
 * heading_deg. The icon atlas is a single SVG pointing north (0°); Deck.gl
 * rotates it clockwise, which matches compass bearing convention.
 *
 * When heading_deg is unavailable (null/undefined), the icon shows north-up
 * as a neutral fallback rather than a misleading direction.
 *
 * Returns null when the aircraft layer is toggled off in the UI store.
 */

import { useMemo } from 'react'
import { IconLayer } from '@deck.gl/layers'
import type { PickingInfo } from '@deck.gl/core'
import { useEntitiesStore } from '../../store/entities.store'
import { useUiStore } from '../../store/ui.store'
import type { NormalizedEntity } from '../../types/entities'

// Single-icon atlas: a 64×64 SVG of an aircraft pointing north.
// Served from /public so Vite copies it to dist/ on build.
const ICON_ATLAS = '/aircraft-icon.svg'
const ICON_MAPPING = {
  aircraft: { x: 0, y: 0, width: 64, height: 64, mask: true },
}

interface Props {
  onPick?: (info: PickingInfo) => void
}

export function useAircraftLayer({ onPick }: Props = {}) {
  const visible  = useUiStore((s) => s.layers.aircraft)
  const entities = useEntitiesStore((s) => s.entities)

  const aircraft = useMemo(
    () =>
      visible
        ? ([...entities.values()].filter((e) => e.entity_type === 'aircraft') as NormalizedEntity[])
        : [],
    [entities, visible],
  )

  return useMemo(
    () =>
      new IconLayer<NormalizedEntity>({
        id: 'aircraft',
        data: aircraft,
        iconAtlas:   ICON_ATLAS,
        iconMapping: ICON_MAPPING,
        getIcon:     () => 'aircraft',
        getPosition: (e) => [e.lon, e.lat, e.alt_m ?? 0],
        // getAngle: deck.gl rotates counter-clockwise in degrees.
        // heading_deg is clockwise from north, so negate it.
        getAngle:    (e) => -(e.heading_deg ?? 0),
        getSize:     28,
        sizeMinPixels: 14,
        sizeMaxPixels: 40,
        // mask:true + getColor lets us tint the white SVG silhouette
        getColor:    [0, 210, 255, 220],
        pickable:    true,
        onClick:     onPick,
        updateTriggers: {
          getPosition: aircraft,
          getAngle:    aircraft,
        },
      }),
    [aircraft, onPick],
  )
}
