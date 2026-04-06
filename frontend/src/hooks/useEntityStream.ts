/**
 * useEntityStream — connects the WebSocket to the entity store.
 *
 * Responsibilities:
 *  1. Dispatch incoming WS messages (snapshot / update / remove) to the store.
 *  2. Run the TTL pruner on a 5-second interval to evict stale entities.
 *  3. Expose a `sendViewport` function so the map can tell the server which
 *     geographic area the user is viewing (server uses this to filter updates).
 *
 * Usage:
 *   const { sendViewport } = useEntityStream()
 *   // Call sendViewport([minLat, minLon, maxLat, maxLon]) on every map move.
 */

import { useCallback, useEffect } from 'react'
import { useWebSocket } from './useWebSocket'
import { useEntitiesStore } from '../store/entities.store'
import type { WsMessage } from '../types/entities'

export function useEntityStream() {
  const applySnapshot = useEntitiesStore((s) => s.applySnapshot)
  const applyUpdate   = useEntitiesStore((s) => s.applyUpdate)
  const removeEntity  = useEntitiesStore((s) => s.removeEntity)
  const pruneStale    = useEntitiesStore((s) => s.pruneStale)

  const handleMessage = useCallback(
    (msg: WsMessage) => {
      switch (msg.type) {
        case 'snapshot':
          applySnapshot(msg.entities)
          break
        case 'update':
          applyUpdate(msg.entity)
          break
        case 'remove':
          removeEntity(msg.id)
          break
      }
    },
    [applySnapshot, applyUpdate, removeEntity],
  )

  const { send } = useWebSocket(handleMessage)

  // Prune stale entities every 5 seconds as a safety net for sources that
  // don't emit explicit "remove" messages (AIS in particular).
  useEffect(() => {
    const id = setInterval(pruneStale, 5_000)
    return () => clearInterval(id)
  }, [pruneStale])

  /**
   * Tell the server which part of the map is currently visible.
   * The Go hub uses this to skip sending updates for entities outside the view.
   *
   * bbox format: [minLat, minLon, maxLat, maxLon]
   */
  const sendViewport = useCallback(
    (bbox: [number, number, number, number]) => {
      send(JSON.stringify({ type: 'setViewport', bbox }))
    },
    [send],
  )

  return { sendViewport }
}
