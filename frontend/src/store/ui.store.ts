/**
 * UI store — controls which map layers are visible.
 *
 * Each layer has a boolean toggle. The layer components read from here
 * and return null (render nothing) when their layer is disabled.
 * The LayerToggle panel (Step 12) writes to here.
 */

import { create } from 'zustand'

interface UiState {
  layers: {
    aircraft: boolean
    ships: boolean
    satellites: boolean
    gpsJam: boolean
    events: boolean
  }
  toggleLayer: (layer: keyof UiState['layers']) => void
}

export const useUiStore = create<UiState>((set) => ({
  layers: {
    aircraft: true,
    ships: true,
    satellites: false, // off by default — large dataset, enable in Step 9
    gpsJam: false, // off by default — heavy h3-js bundle, enable in Step 8
    events: true,
  },

  toggleLayer: (layer) =>
    set((state) => ({
      layers: { ...state.layers, [layer]: !state.layers[layer] },
    })),
}))
