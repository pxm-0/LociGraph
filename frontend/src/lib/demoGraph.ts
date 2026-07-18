import type { PlanetariumNode } from "./types"

// Synthetic planetarium graph for the public landing hero. Real archive data
// stays private, so this is hand-shaped, deterministic (no Math.random at
// import), and matches the PlanetariumNode shape in types.ts exactly.

const LABELS = [
  "Memory",
  "Identity",
  "Time",
  "Language",
  "Ethics",
  "Perception",
  "Causality",
  "Emotion",
  "Knowledge",
  "Intention",
  "Trust",
  "Change",
  "Pattern",
  "Meaning",
  "Attention",
  "Belief",
  "Emergence",
  "Constraint",
  "Signal",
  "Context",
  "Abstraction",
  "Feedback",
  "Boundary",
  "Uncertainty",
  "Value",
  "Structure",
  "Narrative",
  "Judgment",
  "Scale",
  "Resonance",
  "Threshold",
  "Continuity",
  "Recursion",
  "Symmetry",
  "Tension",
  "Origin",
  "Horizon",
  "Drift",
  "Anchor",
  "Field",
]

const GOLDEN_ANGLE = 2.399963229728653 // radians; spreads points evenly

function makeNode(i: number): PlanetariumNode {
  // Deterministic spherical-ish spread using the golden-angle spiral.
  const t = i / LABELS.length
  const theta = i * GOLDEN_ANGLE
  const phi = Math.acos(1 - 2 * t)
  const radius = 8 + (i % 7) * 2
  const x = radius * Math.sin(phi) * Math.cos(theta)
  const y = radius * Math.sin(phi) * Math.sin(theta)
  const z = radius * Math.cos(phi)

  // Every 12th node is a heavy "black hole"; guarantees >= 2 across 40 nodes.
  const isBlackHole = i % 12 === 0
  const mass = isBlackHole ? 3.2 + (i % 3) * 0.4 : 0.6 + (i % 5) * 0.25
  const nodeRadius = isBlackHole ? 1.4 : 0.5 + (i % 4) * 0.15

  return {
    id: `demo-${i}`,
    conceptId: `demo-concept-${i}`,
    conceptName: LABELS[i],
    conceptType: isBlackHole ? "theme" : "concept",
    x,
    y,
    z,
    theta,
    phi,
    radius: nodeRadius,
    mass,
    brightness: 0.4 + (i % 6) * 0.1,
    color: "#4fa3e3",
    visualClass: isBlackHole ? "black_hole" : "planet",
    projectionVersion: "demo",
    projectionAlgorithm: "golden-spiral",
    createdAt: null,
  }
}

export const DEMO_NODES: PlanetariumNode[] = LABELS.map((_, i) => makeNode(i))
