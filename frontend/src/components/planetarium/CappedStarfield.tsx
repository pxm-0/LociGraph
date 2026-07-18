"use client"

import { useRef } from "react"
import { Canvas, useFrame } from "@react-three/fiber"
import { Bounds, Stars } from "@react-three/drei"
import type { Group } from "three"
import type { PlanetariumNode } from "@/lib/types"
import type { Mode } from "@/lib/theme"
import { PlanetNode } from "./PlanetNode"

// Capped & calm 3D surface shared by the landing hero and the dashboard
// mini-planetarium. Unlike PlanetariumScene it has NO OrbitControls and an
// optional slow auto-drift — tuned so these secondary surfaces stay smooth.
// Takes `mode` as a prop (not useMode) so it can render on the landing route,
// which lives outside the app's ThemeProvider.

const PALETTE = {
  meridian: { bg: "#141210", planet: "#4fa3e3", blackHole: "#f4a63c", stars: true },
  hearth: { bg: "#f4fbfa", planet: "#2f72c4", blackHole: "#cc7a1e", stars: false },
} as const

const DRIFT_RADIANS_PER_SEC = 0.06

function DriftGroup({ children }: { children: React.ReactNode }) {
  const ref = useRef<Group>(null)
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.y += delta * DRIFT_RADIANS_PER_SEC
  })
  return <group ref={ref}>{children}</group>
}

interface CappedStarfieldProps {
  nodes: PlanetariumNode[]
  mode?: Mode
  drift?: boolean
}

// onSelect is a no-op: these surfaces are display-only (the full /planetarium
// remains the interactive view).
const noop = () => {}

export function CappedStarfield({ nodes, mode = "meridian", drift = false }: CappedStarfieldProps) {
  const palette = PALETTE[mode]

  const field = (
    <Bounds fit observe margin={1.2}>
      {nodes.map((node) => (
        <PlanetNode
          key={node.id}
          node={node}
          color={node.visualClass === "black_hole" ? palette.blackHole : palette.planet}
          onSelect={noop}
        />
      ))}
    </Bounds>
  )

  return (
    <Canvas camera={{ position: [0, 0, 30], fov: 60 }} style={{ width: "100%", height: "100%" }}>
      <color attach="background" args={[palette.bg]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[10, 10, 10]} intensity={1} />
      {palette.stars && <Stars radius={100} depth={50} count={2000} factor={4} fade />}
      {drift ? <DriftGroup>{field}</DriftGroup> : field}
    </Canvas>
  )
}
