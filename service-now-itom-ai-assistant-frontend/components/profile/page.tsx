import type { Metadata } from 'next'
import { Navbar } from '@/components/navbar'
import { Footer } from '@/components/footer'
import { ProfileView } from '@/components/profile/profile-view'

export const metadata: Metadata = {
  title: 'Your profile · ServiceNow ITOM AI Assistant',
  description: 'Manage your account, photo, and password.',
}

export default function ProfilePage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <Navbar />
      <main className="flex-1">
        <ProfileView />
      </main>
      <Footer />
    </div>
  )
}