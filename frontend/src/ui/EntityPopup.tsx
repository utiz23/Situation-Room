/**
 * EntityPopup — metadata panel shown when a map feature is clicked.
 *
 * Accepts a PickInfo object from Deck.gl's onClick. Renders different
 * fields depending on whether the clicked item is a NormalizedEntity
 * (aircraft / ship / satellite) or a MapEvent (pinned incident).
 *
 * Positioned at the click pixel, clamped so it never goes off-screen.
 * Dismissed by clicking the × button or clicking elsewhere on the map.
 */

import type { NormalizedEntity } from '../types/entities'
import type { MapEvent } from '../types/layers'
import type { SatellitePosition } from '../workers/satellite-propagator.worker'

export type PopupTarget =
  | { kind: 'entity';    data: NormalizedEntity }
  | { kind: 'event';     data: MapEvent }
  | { kind: 'satellite'; data: SatellitePosition }

interface Props {
  target: PopupTarget
  x: number
  y: number
  onClose: () => void
}

function fmt(v: number | undefined | null, unit: string, decimals = 0): string {
  if (v == null) return '—'
  return `${v.toFixed(decimals)} ${unit}`
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toUTCString().replace(' GMT', ' UTC')
  } catch {
    return iso
  }
}

function EntityFields({ e }: { e: NormalizedEntity }) {
  return (
    <>
      <Row label="ID"       value={e.id} />
      <Row label="Type"     value={e.entity_type} />
      <Row label="Source"   value={e.source} />
      {e.callsign  && <Row label="Callsign"  value={e.callsign} />}
      <Row label="Lat"      value={fmt(e.lat, '°', 4)} />
      <Row label="Lon"      value={fmt(e.lon, '°', 4)} />
      {e.alt_m        != null && <Row label="Altitude"  value={fmt(e.alt_m, 'm')} />}
      {e.heading_deg  != null && <Row label="Heading"   value={fmt(e.heading_deg, '°')} />}
      {e.speed_knots  != null && <Row label="Speed"     value={fmt(e.speed_knots, 'kn', 1)} />}
      <Row label="Updated" value={fmtTime(e.timestamp)} />
      {Object.entries(e.metadata).slice(0, 5).map(([k, v]) => (
        <Row key={k} label={k} value={String(v)} />
      ))}
    </>
  )
}

function EventFields({ e }: { e: MapEvent }) {
  return (
    <>
      <Row label="Type"        value={e.event_type.replace('_', ' ')} />
      <Row label="Title"       value={e.title} />
      {e.description && <Row label="Details"     value={e.description} />}
      <Row label="Event time"  value={fmtTime(e.event_time)} />
      <Row label="Lat"         value={fmt(e.lat, '°', 4)} />
      <Row label="Lon"         value={fmt(e.lon, '°', 4)} />
      {e.source_url  && <Row label="Source" value={<a href={e.source_url} target="_blank" rel="noreferrer" style={{ color: '#7cf' }}>link</a>} />}
      {e.contributor && <Row label="By"     value={e.contributor} />}
      <Row label="Verified"    value={e.verified ? 'Yes' : 'No'} />
    </>
  )
}

function SatelliteFields({ s }: { s: SatellitePosition }) {
  return (
    <>
      <Row label="Name"     value={s.name} />
      <Row label="ID"       value={s.id} />
      <Row label="Lat"      value={fmt(s.lat, '°', 4)} />
      <Row label="Lon"      value={fmt(s.lon, '°', 4)} />
      <Row label="Altitude" value={fmt(s.alt_m / 1000, 'km', 0)} />
    </>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 8, fontSize: 12, lineHeight: '18px', wordBreak: 'break-word' }}>
      <span style={{ color: '#aaa', minWidth: 72, flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#eee' }}>{value}</span>
    </div>
  )
}

export function EntityPopup({ target, x, y, onClose }: Props) {
  // Clamp so the panel stays within the viewport (assumes panel ~240×280px)
  const PANEL_W = 260
  const PANEL_H = 300
  const left = Math.max(8, Math.min(x + 12, window.innerWidth - PANEL_W - 8))
  const top  = Math.min(y - 12, window.innerHeight - PANEL_H - 8)

  const title =
    target.kind === 'entity'    ? (target.data.callsign ?? target.data.id) :
    target.kind === 'event'     ? target.data.title :
    target.data.name

  return (
    <div
      style={{
        position:       'absolute',
        left,
        top:            Math.max(8, top),
        width:          PANEL_W,
        maxHeight:      PANEL_H,
        overflowY:      'auto',
        background:     '#1a1a1aee',
        border:         '1px solid #444',
        borderRadius:   8,
        padding:        '10px 12px',
        zIndex:         20,
        backdropFilter: 'blur(6px)',
        fontFamily:     'system-ui, monospace, sans-serif',
        pointerEvents:  'auto',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ color: '#fff', fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200 }}>
          {title}
        </span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0 }}
        >
          ×
        </button>
      </div>

      {/* Fields */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {target.kind === 'entity'    && <EntityFields    e={target.data} />}
        {target.kind === 'event'     && <EventFields     e={target.data} />}
        {target.kind === 'satellite' && <SatelliteFields s={target.data} />}
      </div>
    </div>
  )
}
