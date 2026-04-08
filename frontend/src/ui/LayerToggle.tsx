/**
 * LayerToggle — fixed-position panel for toggling map layers on/off.
 *
 * Positioned bottom-left so it doesn't obscure the map center.
 * Each button reflects the current visibility state from ui.store and
 * calls toggleLayer on click. No external state needed.
 */

import { useUiStore } from '../store/ui.store'

type LayerKey = 'aircraft' | 'ships' | 'satellites' | 'gpsJam' | 'events'

const LAYERS: { key: LayerKey; label: string; color: string }[] = [
  { key: 'aircraft',   label: '✈ Aircraft',   color: '#00d2ff' },
  { key: 'ships',      label: '⛵ Ships',      color: '#ffa000' },
  { key: 'satellites', label: '🛰 Satellites', color: '#ffdc32' },
  { key: 'gpsJam',     label: '📡 GPS Jam',    color: '#ff6600' },
  { key: 'events',     label: '📍 Events',     color: '#dc1e1e' },
]

export function LayerToggle() {
  const layers     = useUiStore((s) => s.layers)
  const toggleLayer = useUiStore((s) => s.toggleLayer)

  return (
    <div style={{
      position:        'absolute',
      bottom:          24,
      left:            16,
      display:         'flex',
      flexDirection:   'column',
      gap:             6,
      zIndex:          10,
      pointerEvents:   'auto',
    }}>
      {LAYERS.map(({ key, label, color }) => {
        const active = layers[key]
        return (
          <button
            key={key}
            onClick={() => toggleLayer(key)}
            title={active ? `Hide ${label}` : `Show ${label}`}
            style={{
              padding:         '6px 12px',
              borderRadius:    6,
              border:          `2px solid ${active ? color : '#555'}`,
              background:      active ? `${color}22` : '#11111188',
              color:           active ? color : '#888',
              cursor:          'pointer',
              fontSize:        13,
              fontWeight:      active ? 600 : 400,
              fontFamily:      'system-ui, sans-serif',
              backdropFilter:  'blur(4px)',
              transition:      'all 0.15s',
              minWidth:        130,
              textAlign:       'left',
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
