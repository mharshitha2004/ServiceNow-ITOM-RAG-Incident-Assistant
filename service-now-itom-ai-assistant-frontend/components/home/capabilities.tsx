import { MessageSquareText } from 'lucide-react'
import { SECTION_SPARKS, Sparks } from '@/components/chat-backdrop'

const steps = [
  { title: 'Describe the issue', description: 'Type the problem in plain language, or paste an error screenshot.' },
  { title: 'Get an answer with sources', description: 'The ITOM documentation and Community articles are checked first. You see the answer and the sections it is based on.' },
  { title: 'Escalate when you need to', description: 'Still stuck? Confirm, then choose P3 or P4. If you pick an unsupported priority, you are simply asked again.' },
  { title: 'Incident created', description: 'The incident is created in ServiceNow with you as the caller, and you get the incident number back.' },
  { title: 'Stay in the loop', description: 'Come back anytime to check its status and work notes, close it once it is fixed, or reopen it if it is not.' },
]

const examples = [
  'Why is my MID Server showing as Down?',
  'A Discovery schedule finished but found no CIs. What should I check?',
  'How do I set up an event rule for a monitored server?',
  'What credentials does Discovery need for Windows servers?',
  'How do I fix duplicate CIs in the CMDB?',
  'What is Software Asset Management?',
  "What's the status of my incident?",
  'Close my incident, the fix worked.',
]

export function Capabilities() {
  return (
    <section className="relative isolate overflow-hidden border-t border-border bg-secondary/30 py-20 sm:py-24">
      <Sparks items={SECTION_SPARKS} />
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="grid gap-14 lg:grid-cols-[1fr_1.05fr] lg:items-start">
          <div>
            <h2 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
              Less searching.
              <br className="hidden sm:block" /> More solving.
            </h2>
            <p className="mt-4 max-w-md text-base leading-7 text-muted-foreground">
              Spend your time fixing the problem, not hunting through pages of documentation.
            </p>

            <ol className="mt-10">
              {steps.map((step, i) => {
                const last = i === steps.length - 1
                return (
                  <li key={step.title} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <span className="flex size-8 shrink-0 items-center justify-center rounded-full border border-primary/30 bg-primary/10 text-xs font-semibold text-primary">
                        {i + 1}
                      </span>
                      {!last && <span className="my-2 w-px flex-1 bg-border" aria-hidden="true" />}
                    </div>
                    <div className={last ? '' : 'pb-8'}>
                      <h3 className="text-base font-semibold text-foreground">{step.title}</h3>
                      <p className="mt-1.5 max-w-md text-sm leading-6 text-muted-foreground">{step.description}</p>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>

          <div className="rounded-2xl border border-border bg-card/50 p-5 sm:p-6">
            <p className="text-sm font-semibold text-foreground">Things you can ask</p>
            <p className="mt-1 text-sm text-muted-foreground">Real questions ITOM admins and operators run into.</p>
            <ul className="mt-5 space-y-3">
              {examples.map((q) => (
                <li key={q} className="flex items-start gap-3 rounded-xl border border-border bg-secondary/40 p-3.5">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary" aria-hidden="true">
                    <MessageSquareText className="size-4" />
                  </span>
                  <span className="pt-1 text-sm leading-5 text-card-foreground">{q}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}