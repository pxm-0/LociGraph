import { Card } from "@/components/ui/Card"
import { LoginForm } from "./login-form"

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-archive px-4">
      <Card className="w-full max-w-sm p-8">
        <div className="mb-8 text-center">
          <h1 className="font-heading text-2xl font-semibold text-dust">LociGraph</h1>
          <p className="mt-1 font-ui text-sm text-ash">Knowledge Archive</p>
        </div>
        <LoginForm />
      </Card>
    </div>
  )
}
