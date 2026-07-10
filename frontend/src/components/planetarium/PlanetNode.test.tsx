import { expect, test } from "vitest"
import { buildConceptHref } from "./PlanetNode"

test("buildConceptHref routes to the concept detail page", () => {
  expect(buildConceptHref("c-123")).toBe("/concepts/c-123")
})
