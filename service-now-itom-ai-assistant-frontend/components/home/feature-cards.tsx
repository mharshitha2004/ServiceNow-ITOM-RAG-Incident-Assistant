import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ArrowRight, BookOpen, ScanSearch, ShieldCheck, UserCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { SECTION_SPARKS, SparkCluster, Sparks } from '@/components/chat-backdrop'

function Flow({ steps }: { steps: string[] }) {
  return (
    <div className="mt-6 flex flex-wrap items-center gap-2">
      {steps.map((step, i) => {
        const last = i === steps.length - 1
        return (
          <div key={step} className="flex items-center gap-2">
            <span
              className={cn(
                'rounded-lg border px-3 py-1.5 text-xs font-medium',
                last ? 'border-primary/30 bg-primary/10 text-primary' : 'border-border bg-secondary/40 text-card-foreground',
              )}
            >
              {step}
            </span>
            {!last && <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden="true" />}
          </div>
        )
      })}
    </div>
  )
}

function PriorityPills() {
  const priorities = [
    { label: 'P1', allowed: false },
    { label: 'P2', allowed: false },
    { label: 'P3', allowed: true },
    { label: 'P4', allowed: true },
  ]
  return (
    <div className="mt-6 flex flex-wrap items-center gap-2">
      {priorities.map(({ label, allowed }) => (
        <span
          key={label}
          className={cn(
            'rounded-lg border px-3.5 py-1.5 text-xs font-semibold',
            allowed
              ? 'border-primary/35 bg-primary/10 text-primary'
              : 'border-border bg-secondary/20 text-muted-foreground line-through',
          )}
        >
          {label}
        </span>
      ))}
      <span className="ml-1 text-xs text-muted-foreground">P1 and P2 follow your standard process</span>
    </div>
  )
}

function FeatureCard({
  icon: Icon, label, title, description, className, children,
}: {
  icon: LucideIcon
  label: string
  title: string
  description: string
  className?: string
  children?: ReactNode
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-border bg-card/60 p-6 transition-colors duration-300 hover:border-primary/30 sm:p-7',
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary" aria-hidden="true">
          <Icon className="size-5" />
        </span>
        <span className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</span>
      </div>
      <h3 className="mt-6 text-xl font-semibold tracking-tight text-foreground">{title}</h3>
      <p className="mt-3 max-w-lg text-sm leading-6 text-muted-foreground">{description}</p>
      {children}
    </div>
  )
}

export function FeatureCards() {
  return (
    <section className="relative isolate overflow-hidden border-t border-border py-20 sm:py-24">
      <Sparks items={SECTION_SPARKS} />
      <div className="relative mx-auto max-w-6xl px-4 sm:px-6">
        <SparkCluster className="absolute right-6 top-0" />
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            From question to resolution
          </h2>
          <p className="mt-4 text-base leading-7 text-muted-foreground">
            Find the information you need, understand what is happening, and raise the incident when the
            documentation is not enough — without switching between tools.
          </p>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-3">
          <FeatureCard
            className="md:col-span-2"
            icon={BookOpen}
            label="Knowledge"
            title="Ask your ITOM documentation"
            description="Ask in plain language about Discovery, CMDB, Event Management, MID Servers and more. Every answer shows the documentation sections it came from, so you can verify before you act."
          >
            <Flow steps={['Ask a question', 'Read the answer']} />
          </FeatureCard>

          <FeatureCard
            icon={ScanSearch}
            label="Troubleshooting"
            title="Start from a screenshot"
            description="Paste or attach an error screenshot and get the relevant troubleshooting steps."
          >
            <Flow steps={['Screenshot', 'Fix steps']} />
          </FeatureCard>

          <FeatureCard
            icon={ShieldCheck}
            label="Incidents"
            title="The full lifecycle, not just creation"
            description="The assistant offers to create a P3 or P4 incident, always asking first. After that, check its status, read the latest work notes, close it once it's fixed, or reopen it if it isn't - all in the same conversation."
          >
            <PriorityPills />
          </FeatureCard>

          <FeatureCard
            className="md:col-span-2"
            icon={UserCheck}
            label="Your account"
            title="Raised as you, not a shared account"
            description="Register with your ServiceNow username. Every incident is created with you as the caller, so it lands in your queue and your history."
          >
            <Flow steps={['Your ServiceNow user', 'Incident created', 'Caller = you']} />
          </FeatureCard>
        </div>
      </div>
    </section>
  )
}