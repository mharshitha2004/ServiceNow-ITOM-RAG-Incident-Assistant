import type { Metadata } from 'next'
import { Navbar } from '@/components/navbar'
import { DocChat } from '@/components/documentation/doc-chat'

export const metadata: Metadata = {
  title: 'Documentation Assistant · ServiceNow ITOM AI Assistant',
  description:
    'Chat with the product documentation assistant to find answers, explore troubleshooting guides, and discover relevant documentation.',
}

export default function DocumentationPage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <Navbar />
      <main className="flex-1">
        <DocChat />
      </main>
    </div>
  )
}
