import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import type { Job } from "@/lib/types"

vi.mock("@/lib/api", () => ({ rebuildPlanetarium: vi.fn(), getJob: vi.fn() }))

import { getJob, rebuildPlanetarium } from "@/lib/api"
import { RebuildButton } from "./RebuildButton"

const mockRebuild = vi.mocked(rebuildPlanetarium)
const mockGetJob = vi.mocked(getJob)

function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job-1",
    jobType: "project_planetarium",
    status: "running",
    attempts: 0,
    error: null,
    createdAt: null,
    startedAt: null,
    completedAt: null,
    itemsCompleted: null,
    itemsTotal: null,
    sourceId: null,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})
afterEach(() => {
  vi.useRealTimers()
})

test("triggers a rebuild and calls onRebuildComplete once the job completes", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockRebuild.mockResolvedValueOnce({ jobId: "job-1", status: "pending" })
  mockGetJob.mockResolvedValueOnce(makeJob({ status: "completed" }))
  const onRebuildComplete = vi.fn()

  render(<RebuildButton onRebuildComplete={onRebuildComplete} />)
  await userEvent.click(screen.getByRole("button", { name: /rebuild planetarium/i }), {
    delay: null,
  })
  await vi.waitFor(() => expect(mockRebuild).toHaveBeenCalled())

  await vi.advanceTimersByTimeAsync(1200)
  await vi.waitFor(() => expect(onRebuildComplete).toHaveBeenCalled())
})

test("shows the job's error message when the rebuild job fails", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockRebuild.mockResolvedValueOnce({ jobId: "job-1", status: "pending" })
  mockGetJob.mockResolvedValueOnce(makeJob({ status: "failed", error: "boom" }))

  render(<RebuildButton onRebuildComplete={vi.fn()} />)
  await userEvent.click(screen.getByRole("button", { name: /rebuild planetarium/i }), {
    delay: null,
  })
  await vi.advanceTimersByTimeAsync(1200)

  expect(await screen.findByRole("alert")).toHaveTextContent("boom")
})

test("disables the button while a rebuild is running", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  mockRebuild.mockResolvedValueOnce({ jobId: "job-1", status: "pending" })
  mockGetJob.mockResolvedValueOnce(makeJob({ status: "completed" }))

  render(<RebuildButton onRebuildComplete={vi.fn()} />)
  const button = screen.getByRole("button", { name: /rebuild planetarium/i })
  await userEvent.click(button, { delay: null })

  expect(button).toBeDisabled()
  await vi.advanceTimersByTimeAsync(1200)
  await vi.waitFor(() => expect(button).not.toBeDisabled())
})
