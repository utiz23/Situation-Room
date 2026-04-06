/**
 * Events store — holds admin-pinned incidents fetched from REST + pushed via WS.
 *
 * Populated two ways:
 *  1. On mount: fetched from GET /api/events (full list).
 *  2. Live: when the server pushes {"type":"event",...} over WebSocket after
 *     an admin creates a new event via POST /api/events.
 *
 * useEntityStream dispatches the WS "event" messages here so EventLayer
 * never has to open its own WebSocket connection.
 */

import { create } from 'zustand'
import type { MapEvent } from '../types/layers'

interface EventsState {
  events: MapEvent[]
  setEvents: (events: MapEvent[]) => void
  addEvent: (event: MapEvent) => void
}

export const useEventsStore = create<EventsState>((set, get) => ({
  events: [],

  setEvents: (events) => set({ events }),

  addEvent: (event) => {
    // Deduplicate: ignore if we already have this event ID
    if (get().events.some((e) => e.id === event.id)) return
    set((state) => ({ events: [event, ...state.events] }))
  },
}))
