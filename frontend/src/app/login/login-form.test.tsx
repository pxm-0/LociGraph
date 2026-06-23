import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, test, vi } from "vitest"

const push = vi.fn()
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: push, push }) }))
const login = vi.fn().mockResolvedValue({ userId: "u1" })
vi.mock("@/lib/api", () => ({ login: (...a: unknown[]) => login(...a), ApiError: class extends Error {} }))

import { LoginForm } from "./login-form"

test("submits password and redirects to dashboard on success", async () => {
  render(<LoginForm />)
  await userEvent.type(screen.getByLabelText(/password/i), "secret")
  await userEvent.click(screen.getByRole("button", { name: /enter archive/i }))
  expect(login).toHaveBeenCalledWith("secret")
})

test("shows an error message on 401", async () => {
  login.mockRejectedValueOnce(Object.assign(new Error("bad"), { status: 401 }))
  render(<LoginForm />)
  await userEvent.type(screen.getByLabelText(/password/i), "nope")
  await userEvent.click(screen.getByRole("button", { name: /enter archive/i }))
  expect(await screen.findByRole("alert")).toBeInTheDocument()
})
