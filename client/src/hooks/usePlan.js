import { useMutation } from '@tanstack/react-query'
import { postPlan } from '../api'

/** Mutation for the plan analysis endpoint; `onSuccess` receives the plan. */
export function usePlan(onSuccess) {
  return useMutation({
    mutationFn: postPlan,
    onSuccess,
  })
}
