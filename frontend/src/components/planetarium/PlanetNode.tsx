"use client"

import { useRouter } from "next/navigation"
import type { ThreeEvent } from "@react-three/fiber"
import type { PlanetariumNode } from "@/lib/types"

export function buildConceptHref(conceptId: string): string {
  return `/concepts/${conceptId}`
}

interface PlanetNodeProps {
  node: PlanetariumNode
}

export function PlanetNode({ node }: PlanetNodeProps) {
  const router = useRouter()

  function handleClick(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation()
    router.push(buildConceptHref(node.conceptId))
  }

  return (
    <mesh position={[node.x, node.y, node.z]} onClick={handleClick}>
      <icosahedronGeometry args={[node.radius, 1]} />
      <meshStandardMaterial color={node.color} flatShading />
    </mesh>
  )
}
