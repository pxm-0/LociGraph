import ImportForm from "./import-form"

export default function ImportPage() {
  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="font-heading text-2xl font-medium text-ink">
          Import Source
        </h1>
        <p className="mt-1 font-ui text-sm text-muted">
          Upload a file to begin ingestion into the archive.
        </p>
      </div>
      <ImportForm />
    </div>
  )
}
