import SituationMap from './map/SituationMap'

// App is intentionally thin — SituationMap owns the full-screen canvas.
// Future steps will add a layer toggle panel and entity popup here.
export default function App() {
  return <SituationMap />
}
