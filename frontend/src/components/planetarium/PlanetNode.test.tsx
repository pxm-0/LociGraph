import { expect, test } from "vitest"
import { hoverLabelFor } from "./PlanetNode"

test("hoverLabelFor returns the concept's name", () => {
  expect(hoverLabelFor({ conceptName: "Alpha" } as never)).toBe("Alpha")
})
