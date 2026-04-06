/**
 * useWebSocket — low-level WebSocket connection with automatic reconnection.
 *
 * Connects to /ws (proxied by Vite to ws://localhost:8080/ws in dev).
 * When the connection drops (browser offline, server restart, etc.) it
 * reconnects with exponential backoff: 1 s, 2 s, 4 s, 8 s, 16 s, 30 s max.
 *
 * Returns a `send` function for sending messages to the server (e.g. setViewport).
 *
 * Usage:
 *   const { send } = useWebSocket((msg) => console.log(msg))
 */

import { useCallback, useEffect, useRef } from 'react'
import type { WsMessage } from '../types/entities'

const WS_URL = '/ws' // Vite proxies this to ws://localhost:8080/ws in dev
const MAX_RETRY_DELAY_MS = 30_000

export function useWebSocket(onMessage: (msg: WsMessage) => void) {
  // Keep the latest onMessage callback in a ref so reconnecting doesn't
  // require tearing down and recreating the WebSocket.
  const onMessageRef = useRef(onMessage)
  useEffect(() => {
    onMessageRef.current = onMessage
  })

  const wsRef = useRef<WebSocket | null>(null)
  const retriesRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountedRef = useRef(false)

  const connect = useCallback(() => {
    if (unmountedRef.current) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      retriesRef.current = 0
      console.log('[ws] connected')
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage
        onMessageRef.current(msg)
      } catch {
        console.warn('[ws] malformed message', event.data)
      }
    }

    ws.onclose = () => {
      if (unmountedRef.current) return
      const delay = Math.min(1_000 * 2 ** retriesRef.current, MAX_RETRY_DELAY_MS)
      retriesRef.current++
      console.log(`[ws] closed — reconnecting in ${delay}ms (attempt ${retriesRef.current})`)
      retryTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      // onclose fires after onerror; reconnect logic lives there.
      console.warn('[ws] error')
    }
  }, []) // stable — never changes

  useEffect(() => {
    unmountedRef.current = false
    connect()

    return () => {
      unmountedRef.current = true
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  /** Send a JSON message to the server. No-ops if the socket isn't open. */
  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  return { send }
}
