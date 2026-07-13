"use client"

import { Canvas } from "@react-three/fiber"
import { Bounds, OrbitControls, Stars } from "@react-three/drei"
import { useMode } from "@/lib/theme"
import type { PlanetariumNode } from "@/lib/types"
import { PlanetNode } from "./PlanetNode"

// Per-theme palette so both canvases stay legible. `bg` mirrors --color-canvas
// in globals.css. Heavy "black hole" nodes take a warm accent so the most
// important concepts pop; planets are the cool field. Stars only make sense on
// the dark canvas — white points vanish on the light one.
const PALETTE = {
  meridian: { bg: "#141210", planet: "#4fa3e3", blackHole: "#f4a63c", stars: true },
  hearth: { bg: "#f4fbfa", planet: "#2f72c4", blackHole: "#cc7a1e", stars: false },
} as const

interface PlanetariumSceneProps {
  nodes: PlanetariumNode[]
}

export function PlanetariumScene({ nodes }: PlanetariumSceneProps) {
  const { mode } = useMode()
  const palette = PALETTE[mode]

  return (
    <Canvas camera={{ position: [0, 0, 30], fov: 60 }} style={{ width: "100%", height: "100%" }}>
      <color attach="background" args={[palette.bg]} />
      <ambientLight intensity={0.7} />
      <directionalLight position={[10, 10, 10]} intensity={1} />
      {palette.stars && <Stars radius={100} depth={50} count={2000} factor={4} fade />}
      <Bounds fit observe margin={1.2}>
        {nodes.map((node) => (
          <PlanetNode
            key={node.id}
            node={node}
            color={node.visualClass === "black_hole" ? palette.blackHole : palette.planet}
          />
        ))}
      </Bounds>
      <OrbitControls makeDefault />
    </Canvas>
  )
}
