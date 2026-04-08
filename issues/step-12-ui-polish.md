# Step 12: UI polish — layer controls, popups, icon refinement

## Goal
Polish the frontend UI for a presentable v1 release. The map works, but the controls and popups need visual refinement.

## Requirements
- **Layer toggle panel**: better styling, hover effects, optional collapse/expand
- **Entity popups**: consistent layout for aircraft, ships, satellites, and events; show relevant fields cleanly
- **Icons**: distinct markers for each entity type (aircraft heading arrow, ship icon, satellite dot, event pin)
- **Responsive layout**: ensure controls don't overlap on smaller viewports
- **Loading state**: show a spinner or skeleton while initial data loads

## Acceptance Criteria
- [ ] Layer toggles look polished with clear active/inactive states
- [ ] Clicking any entity shows a well-formatted popup with relevant data
- [ ] Icons are visually distinct per entity type
- [ ] No layout overflow on 1024x768 viewport
- [ ] Playwright smoke tests still pass after changes
