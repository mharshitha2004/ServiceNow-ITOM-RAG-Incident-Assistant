import Link from 'next/link'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowRight,
  BookOpen,
  Bot,
  Check,
  Cloud,
  Cog,
  Database,
  FileText,
  Network,
  Radar,
  RefreshCw,
  Server,
  ShieldCheck,
  User,
  UserCheck,
  Activity,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { HERO_BAND, HERO_SPARKS, InlineSpark, Sparks } from '@/components/chat-backdrop'

const proofPoints = [
  { icon: BookOpen, text: 'Answers grounded in the official Servicenow ITOM documentation' },
  { icon: ShieldCheck, text: 'You confirm every incident before it is created' },
  { icon: UserCheck, text: 'Incidents are raised under your own ServiceNow user' },
  { icon: RefreshCw, text: 'Check status, close it, or reopen it - all in the chat' },
]

const modules: { icon: LucideIcon; name: string }[] = [
  { icon: Radar, name: 'Discovery' },
  { icon: Database, name: 'CMDB' },
  { icon: Network, name: 'Service Mapping' },
  { icon: Activity, name: 'Event Management' },
  { icon: Server, name: 'Asset Management' },
  { icon: Cloud, name: 'Cloud Operations' },
  { icon: Cog, name: 'Automation' },
]

const tealGradient = 'bg-gradient-to-r from-[#06C6DC] to-[#3FD17A]'
const greenGradient = 'bg-gradient-to-br from-[#9be98b] to-primary'

function AssistantAvatar() {
  return (
    <span
      className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg ${greenGradient} text-slate-950`}
      aria-hidden="true"
    >
      <Bot className="size-3.5" />
    </span>
  )
}

/** Static preview of the real Incident Assistant conversation. */
/** Static preview of the real Incident Assistant conversation. */
function ProductPreview() {
  return (
    <div className="relative mx-auto w-full max-w-[560px]">
      <div
        className="absolute -inset-6 -z-10 rounded-[2rem] bg-primary/[0.07] blur-3xl"
        aria-hidden="true"
      />

      <div className="overflow-hidden rounded-2xl border border-border bg-card/95 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.65)]">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-sm font-medium text-muted-foreground">
            Incident Assistant
          </span>

          <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary">
            <span className="size-1.5 rounded-full bg-primary" />
            Connected to ServiceNow
          </span>
        </div>

        <div className="space-y-4 p-4 sm:p-5">
          <div className="flex justify-end gap-3">
            {/* Fixed dark teal/cyan chip - intentionally the same in both
                themes, like the real chat's user bubble. */}
            <div className="max-w-[85%] rounded-2xl rounded-tr-sm border border-cyan-400/20 bg-gradient-to-br from-teal-700 to-cyan-800 px-4 py-2.5 text-[15px] leading-relaxed text-white">
              My MID Server shows{' '}
              <strong className="font-semibold">Down</strong>{' '}
              after a restart. What should I check?
            </div>

            <span
              className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-secondary"
              aria-hidden="true"
            >
              <User className="size-3.5" />
            </span>
          </div>

          <div className="flex gap-3">
            <AssistantAvatar />

            <div className="min-w-0 flex-1 space-y-2">
              <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 text-[15px] leading-relaxed text-card-foreground">
                Check the agent log for connection errors, verify the instance URL
                and credentials in the MID Server configuration, then restart the
                service and confirm the status returns to{' '}
                <strong className="font-semibold text-foreground">Up</strong>.
              </div>

              <div className="rounded-xl border border-border bg-secondary/40 p-2.5 text-[13px]">
                <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <FileText className="size-4" aria-hidden="true" />
                  From the documentation
                </p>

                <ul className="space-y-1 text-card-foreground">
                  <li>
                    MID Server{' '}
                    <span className="text-muted-foreground">
                      — Configuration parameters
                    </span>
                  </li>

                  <li>
                    MID Server{' '}
                    <span className="text-muted-foreground">
                      — Troubleshooting
                    </span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <AssistantAvatar />

            <div className="min-w-0 flex-1 space-y-2.5">
              <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 text-[15px] leading-relaxed text-card-foreground">
                Still not resolved? I can create a ServiceNow incident for this.
              </div>

              <div className="flex gap-2">
                <span className="rounded-full border border-primary/40 bg-primary/15 px-3.5 py-1 text-[13px] font-semibold text-primary">
                  Yes, create it
                </span>

                <span className="rounded-full border border-border px-3.5 py-1 text-[13px] font-medium text-muted-foreground">
                  No
                </span>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-primary/25 bg-primary/[0.07] p-3.5">
            <div className="flex items-center gap-2 text-[15px] font-semibold text-foreground">
              <span
                className={`flex size-5 items-center justify-center rounded-full ${greenGradient} text-slate-950`}
              >
                <Check className="size-3" strokeWidth={3} aria-hidden="true" />
              </span>

              Incident INC0010042 created
            </div>

            <dl className="mt-3 grid grid-cols-3 gap-3 text-xs">
              <div>
                <dt className="text-muted-foreground">Priority</dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  P3 · Moderate
                </dd>
              </div>

              <div>
                <dt className="text-muted-foreground">Caller</dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  Abel Tuter
                </dd>
              </div>

              <div>
                <dt className="text-muted-foreground">State</dt>
                <dd className="mt-0.5 font-medium text-foreground">
                  New
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      <p className="mt-3 text-center text-[11px] text-muted-foreground">
        Example conversation
      </p>
    </div>
  )
}

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10" aria-hidden="true">
        <Sparks items={HERO_SPARKS} />
        <div className="absolute left-1/2 top-[-260px] h-[560px] w-[980px] -translate-x-1/2 rounded-full bg-primary/[0.08] blur-[140px]" />
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'radial-gradient(color-mix(in oklab, var(--foreground) 7%, transparent) 1px, transparent 1px)',
            backgroundSize: '26px 26px',
            maskImage: 'radial-gradient(ellipse 75% 65% at 50% 0%, #000 25%, transparent 78%)',
            WebkitMaskImage: 'radial-gradient(ellipse 75% 65% at 50% 0%, #000 25%, transparent 78%)',
          }}
        />
      </div>

      <div className="relative mx-auto grid max-w-6xl items-start gap-14 px-4 pb-16 pt-6 sm:px-6 lg:grid-cols-[1fr_1.05fr] lg:pb-20 lg:pt-8">
        <Sparks items={HERO_BAND} />
        <div>
          <div className="flex items-center gap-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/[0.08] px-3 py-1 text-xs font-medium text-primary">
              <span className="size-1.5 rounded-full bg-primary" />
              ServiceNow ITOM · AI Assistant
          </div>
            <InlineSpark size={16} />
            <InlineSpark size={9} color="#12BFCB" delay="1.3s" dur="3.4s" />
          </div>

          <h1 className="mt-6 text-4xl font-semibold leading-[1.08] tracking-tight text-foreground sm:text-5xl lg:text-[3.4rem]">
            From ITOM error to ServiceNow incident,{' '}
            <span className="bg-gradient-to-r from-[#9be98b] to-primary bg-clip-text text-transparent">
              in one conversation.
            </span>{' '}
            <InlineSpark size={30} color="#12BFCB" delay="0.6s" className="inline-block align-middle" />
          </h1>

          <p className="mt-5 max-w-xl text-base leading-7 text-muted-foreground sm:text-base">
            Ask about Discovery, MID Servers, Event Management and more. Get answers cited from the product
            documentation, Community articles — and when the docs aren&apos;t enough, the assistant raises the incident in ServiceNow
            for you. From there, check its status, add an update, close it, or reopen it - all in the same
            conversation.
          </p>

          <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button
              nativeButton={false}
              render={<Link href="/documentation" />}
              className={`group h-12 w-full gap-2 rounded-xl ${tealGradient} px-6 text-base font-semibold text-slate-950 shadow-[0_10px_30px_-10px_rgba(6,198,220,0.55)] transition-all duration-300 hover:-translate-y-0.5 hover:opacity-95 sm:w-auto`}
            >
              <BookOpen className="size-4" />
              Ask the docs
              <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" />
            </Button>
            <Button
              nativeButton={false}
              variant="outline"
              render={<Link href="/incident" />}
              className="group h-12 w-full gap-2 rounded-xl border-border bg-secondary/50 px-6 text-base font-semibold text-foreground transition-all duration-300 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-secondary sm:w-auto"
            >
              Create an incident
              <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" />
            </Button>
          </div>

          <ul className="mt-10 space-y-3">
            {proofPoints.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-3 text-sm text-foreground">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary" aria-hidden="true">
                  <Icon className="size-3.5" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>

        <ProductPreview />
      </div>

      {/* ITOM coverage strip (replaces "Built with") */}
      <div className="border-t border-border">
        <div className="mx-auto max-w-6xl px-4 py-7 sm:px-6">
          <p className="text-sm font-medium text-muted-foreground">Ask about any part of ITOM</p>
          <ul className="mt-4 flex flex-wrap gap-2.5">
            {modules.map(({ icon: Icon, name }) => (
              <li key={name} className="flex items-center gap-2 rounded-xl border border-border bg-secondary/40 px-3.5 py-2 text-sm text-foreground">
                <Icon className="size-4 text-primary" aria-hidden="true" />
                {name}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}