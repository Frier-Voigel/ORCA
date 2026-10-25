import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface PanelProps {
  title: string
  description?: string
  actions?: ReactNode
  className?: string
  bodyClassName?: string
  children: ReactNode
}

export function Panel({ title, description, actions, className, bodyClassName, children }: PanelProps) {
  const id = `panel-${title.toLowerCase().replace(/\s+/g, "-")}`
  return (
    <section aria-labelledby={id} className={cn("flex min-w-0 flex-col rounded-lg border bg-card", className)}>
      <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0">
          <h2 id={id} className="text-sm font-medium text-foreground">
            {title}
          </h2>
          {description ? <p className="truncate text-xs text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className={cn("min-h-0 flex-1 p-4", bodyClassName)}>{children}</div>
    </section>
  )
}
