import { Navbar } from '@/components/navbar'
import { Footer } from '@/components/footer'
import { Hero } from '@/components/home/hero'
import { FeatureCards } from '@/components/home/feature-cards'
import { Capabilities } from '@/components/home/capabilities'

export default function HomePage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <Navbar />
      <main className="flex-1">
        <Hero />
        <FeatureCards />
        <Capabilities />
      </main>
      <Footer />
    </div>
  )
}