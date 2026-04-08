/**
 * EventLayer — renders admin-pinned incidents on the map.
 *
 * Data flow (two sources, one socket):
 *  1. REST: fetches GET /api/events once on mount for the full current list.
 *  2. WebSocket: useEntityStream (the single shared WS connection) dispatches
 *     {"type":"event",...} messages into the events store. New events appear
 *     on all clients instantly when an admin POSTs one.
 *
 * State lives in useEventsStore so EventLayer never opens its own WS connection.
 *
 * Each event renders as a red circle. Step 12 will wire click → EntityPopup.
 *
 * Returns null when the events toggle is off in the UI store.
 */

import { useEffect, useMemo } from 'react'
import { ScatterplotLayer } from '@deck.gl/layers'
import type { Layer, PickingInfo } from '@deck.gl/core'
import { useUiStore } from '../../store/ui.store'
import { useEventsStore } from '../../store/events.store'
import type { MapEvent } from '../../types/layers'

// Red — distinct from aircraft (cyan), ships (orange), satellites (gold)
const EVENT_COLOR: [number, number, number, number] = [220, 30, 30, 230]

interface Props {
  onPick?: (info: PickingInfo) => void
}

export function useEventLayer({ onPick }: Props = {}): Layer | null {
  const visible   = useUiStore((s) => s.layers.events)
  const events    = useEventsStore((s) => s.events)
  const setEvents = useEventsStore((s) => s.setEvents)

  // Fetch the full event list once on mount so events are ready immediately
  // when the layer is toggled on (or if it starts on by default).
  useEffect(() => {
    fetch('/api/events')
      .then((r) => r.json() as Promise<MapEvent[]>)
      .then(setEvents)
      .catch((err) => console.error('[events] fetch failed:', err))
  }, [setEvents])

  return useMemo(() => {
    if (!visible || events.length === 0) return null

    return new ScatterplotLayer<MapEvent>({
      id: 'events',
      data: events,
      getPosition: (e) => [e.lon, e.lat],
      getFillColor: EVENT_COLOR,
      getRadius: 8_000,
      radiusMinPixels: 5,
      radiusMaxPixels: 20,
      pickable: true,
      onClick: onPick,
      updateTriggers: { getPosition: events, getFillColor: events },
    })
  }, [visible, events, onPick])
}
