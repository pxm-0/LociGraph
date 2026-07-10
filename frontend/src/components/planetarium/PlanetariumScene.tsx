"use client"

import { Canvas } from "@react-three/fiber"
import { OrbitControls, Stars } from "@react-three/drei"
import type { PlanetariumNode } from "@/lib/types"
import { PlanetNode } from "./PlanetNode"

interface PlanetariumSceneProps {
  nodes: PlanetariumNode[]
}

export function PlanetariumScene({ nodes }: PlanetariumSceneProps) {
  return (
    <Canvas camera={{ position: [0, 0, 30], fov: 60 }} style={{ width: "100%", height: "100%" }}>
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 10, 10]} intensity={1} />
      <Stars radius={100} depth={50} count={2000} factor={4} fade />
      {nodes.map((node) => (
        <PlanetNode key={node.id} node={node} />
      ))}
      <OrbitControls />
    </Canvas>
  )
}
