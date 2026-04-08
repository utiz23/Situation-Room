import SituationMap from './map/SituationMap'

// App is intentionally thin — SituationMap owns the full-screen canvas.
// The outer div fills the viewport so the map and overlay panels have a
// sized container to position themselves inside.
export default function App() {
  return (
    <div style={{ width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <SituationMap />
    </div>
  )
}
