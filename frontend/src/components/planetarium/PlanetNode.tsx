"use client"

import { useRouter } from "next/navigation"
import type { ThreeEvent } from "@react-three/fiber"
import type { PlanetariumNode } from "@/lib/types"
import { buildConceptHref } from "./ConceptDetailPanel"

interface PlanetNodeProps {
  node: PlanetariumNode
  color: string
}

export function PlanetNode({ node, color }: PlanetNodeProps) {
  const router = useRouter()

  function handleClick(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation()
    router.push(buildConceptHref(node.conceptId))
  }

  // A touch of self-illumination keeps faces angled away from the light
  // readable — on the dark canvas they'd otherwise fall to near-black, and it
  // gives the nodes a faint "glowing body" feel on both themes.
  return (
    <mesh position={[node.x, node.y, node.z]} onClick={handleClick}>
      <icosahedronGeometry args={[node.radius, 1]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.35} flatShading />
    </mesh>
  )
}
