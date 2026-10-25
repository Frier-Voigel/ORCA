"use client"

import useSWR from "swr"
import { fetchState, IS_LIVE } from "@/lib/orca/client"
import type { SystemState } from "@/lib/orca/types"

export function useOrcaState() {
  return useSWR<SystemState>("orca:state", fetchState, {
    refreshInterval: IS_LIVE ? 1000 : 500,
    dedupingInterval: 0,
    keepPreviousData: true,
    revalidateOnFocus: true,
    errorRetryInterval: 3000,
  })
}
