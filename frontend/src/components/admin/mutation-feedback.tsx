import { Notice } from "@/components/ui/notice";

export function MutationFeedback({ error, success }: { error?: string | null; success?: string | null }) {
  if (error) return <div role="alert" aria-live="assertive"><Notice tone="danger">{error}</Notice></div>;
  if (success) return <div role="status" aria-live="polite"><Notice tone="success">{success}</Notice></div>;
  return null;
}
