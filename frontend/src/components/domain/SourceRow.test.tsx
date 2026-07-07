import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import type { Source } from "@/lib/types"
import { SourceRow } from "./SourceRow"

const SOURCE: Source = {
  id: "1",
  sourceType: "json",
  originalFilename: "archive_manifest.json",
  importStatus: "VERIFIED",
  fileSizeBytes: 2048,
  importedAt: null,
  observationCount: 100,
  claimCount: 0,
  claimExtractionStatus: "waiting",
}

function renderRow(props: Partial<React.ComponentProps<typeof SourceRow>> = {}) {
  return render(
    <table>
      <tbody>
        <SourceRow source={SOURCE} {...props} />
      </tbody>
    </table>,
  )
}

describe("SourceRow progress bar", () => {
  it("renders progress text and bar width when extracting with known totals", () => {
    renderRow({ isExtracting: true, itemsCompleted: 5, itemsTotal: 20 })

    expect(screen.getByText("5 / 20 processed")).toBeInTheDocument()
    const bar = screen.getByTestId("extraction-progress-bar")
    expect(bar).toHaveStyle({ width: "25%" })
  })

  it("does not render the progress bar when itemsTotal is null", () => {
    renderRow({ isExtracting: true, itemsCompleted: null, itemsTotal: null })

    expect(screen.queryByTestId("extraction-progress-bar")).not.toBeInTheDocument()
  })

  it("does not render the progress bar when not extracting", () => {
    renderRow({ isExtracting: false, itemsCompleted: 5, itemsTotal: 20 })

    expect(screen.queryByTestId("extraction-progress-bar")).not.toBeInTheDocument()
  })
})

describe("SourceRow embed button", () => {
  it("is disabled when the source has no claims yet", () => {
    renderRow({ onEmbed: () => {} })
    expect(screen.getByRole("button", { name: "Embed" })).toBeDisabled()
  })

  it("is enabled once claims exist and calls onEmbed with the source on click", async () => {
    const onEmbed = vi.fn()
    renderRow({ source: { ...SOURCE, claimCount: 3 }, onEmbed })

    const button = screen.getByRole("button", { name: "Embed" })
    expect(button).not.toBeDisabled()
    await userEvent.click(button)

    expect(onEmbed).toHaveBeenCalledWith(expect.objectContaining({ id: SOURCE.id }))
  })

  it("shows Embedding and disables the button while isEmbedding is true", () => {
    renderRow({ source: { ...SOURCE, claimCount: 3 }, onEmbed: () => {}, isEmbedding: true })
    expect(screen.getByRole("button", { name: "Embedding" })).toBeDisabled()
  })

  it("does not render the embed button when onEmbed is not provided", () => {
    renderRow()
    expect(screen.queryByRole("button", { name: /embed/i })).not.toBeInTheDocument()
  })
})
