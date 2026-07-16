import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, expect, test, vi } from "vitest"
import type { PlanetariumNodeDetail } from "@/lib/types"

vi.mock("@/lib/api", () => ({ getPlanetariumNodeDetail: vi.fn() }))

import { getPlanetariumNodeDetail } from "@/lib/api"
import { buildConceptHref, ConceptDetailPanel } from "./ConceptDetailPanel"

const mockGetDetail = vi.mocked(getPlanetariumNodeDetail)

function detail(overrides: Partial<PlanetariumNodeDetail> = {}): PlanetariumNodeDetail {
  return {
    conceptId: "c1",
    conceptName: "Alpha",
    conceptType: "entity",
    description: null,
    mass: 0.5,
    brightness: 0.5,
    visualClass: "planet",
    revisionCount: 2,
    edgeCount: 3,
    contradictionCount: 0,
    pinCount: 1,
    isEmbedded: true,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

test("buildConceptHref routes to the concept detail page", () => {
  expect(buildConceptHref("c-123")).toBe("/concepts/c-123")
})

test("shows a loading state, then the concept's name and breakdown", async () => {
  mockGetDetail.mockResolvedValueOnce(detail())
  render(<ConceptDetailPanel conceptId="c1" onClose={vi.fn()} />)

  expect(screen.getByText(/loading/i)).toBeInTheDocument()
  expect(await screen.findByText("Alpha")).toBeInTheDocument()
  expect(screen.getByText(/2 revisions/i)).toBeInTheDocument()
  expect(screen.getByText(/3 edges/i)).toBeInTheDocument()
  expect(screen.getByRole("link", { name: /view full concept/i })).toHaveAttribute(
    "href",
    "/concepts/c1"
  )
})

test("flags when a node isn't semantically positioned", async () => {
  mockGetDetail.mockResolvedValueOnce(detail({ isEmbedded: false }))
  render(<ConceptDetailPanel conceptId="c1" onClose={vi.fn()} />)

  expect(await screen.findByText(/not semantically positioned/i)).toBeInTheDocument()
})

test("shows an error message when the fetch fails", async () => {
  mockGetDetail.mockRejectedValueOnce(new Error("boom"))
  render(<ConceptDetailPanel conceptId="c1" onClose={vi.fn()} />)

  expect(await screen.findByRole("alert")).toHaveTextContent("boom")
})

test("calls onClose when the close button is clicked", async () => {
  mockGetDetail.mockResolvedValueOnce(detail())
  const onClose = vi.fn()
  render(<ConceptDetailPanel conceptId="c1" onClose={onClose} />)
  await screen.findByText("Alpha")

  await userEvent.click(screen.getByRole("button", { name: /close/i }))
  expect(onClose).toHaveBeenCalled()
})
