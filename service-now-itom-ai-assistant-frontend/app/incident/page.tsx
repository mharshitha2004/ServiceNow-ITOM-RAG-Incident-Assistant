// app/incident/page.tsx
import type { Metadata } from 'next'
import { Navbar } from '@/components/navbar'
import { IncidentAssistant } from '@/components/incident/incident-assistant'
// Footer import removed - not shown on the chat screen

export const metadata: Metadata = {
  title: 'Incident Assistant · ServiceNow ITOM AI Assistant',
  description:
    'Describe an error, understand the issue, and prepare a structured, review-ready incident draft.',
}

export default function IncidentPage() {
  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <Navbar />
      <main className="min-h-0 flex-1">
        <IncidentAssistant />
      </main>
      {/* No <Footer /> here */}
    </div>
  )
}
