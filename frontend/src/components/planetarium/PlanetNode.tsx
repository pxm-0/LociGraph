"use client"

import { useState } from "react"
import { Html } from "@react-three/drei"
import type { ThreeEvent } from "@react-three/fiber"
import type { PlanetariumNode } from "@/lib/types"

export function hoverLabelFor(node: PlanetariumNode): string {
  return node.conceptName
}

interface PlanetNodeProps {
  node: PlanetariumNode
  color: string
  onSelect: (conceptId: string) => void
}

// A touch of self-illumination keeps faces angled away from the light
// readable — on the dark canvas they'd otherwise fall to near-black, and it
// gives the nodes a faint "glowing body" feel on both themes.
export function PlanetNode({ node, color, onSelect }: PlanetNodeProps) {
  const [hovered, setHovered] = useState(false)

  function handleClick(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation()
    onSelect(node.conceptId)
  }

  return (
    <mesh
      position={[node.x, node.y, node.z]}
      onClick={handleClick}
      onPointerOver={(event: ThreeEvent<PointerEvent>) => {
        event.stopPropagation()
        setHovered(true)
      }}
      onPointerOut={() => setHovered(false)}
    >
      <icosahedronGeometry args={[node.radius, 1]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.35} flatShading />
      {hovered && (
        <Html distanceFactor={10} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded bg-surface px-2 py-1 text-xs text-ink shadow">
            {hoverLabelFor(node)}
          </div>
        </Html>
      )}
    </mesh>
  )
}
