"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api/client";
import type { ActivationResult } from "@/lib/api/types";
import { Button } from "@/components/ui/button";
import { MutationFeedback } from "@/components/admin/mutation-feedback";

export function ConfigActivation() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  async function activate() {
    setBusy(true); setError(null); setSuccess(null);
    try {
      const r = await apiFetch<ActivationResult>("/api/backend/admin/config/activate-due", { method: "POST" });
      setSuccess(`Checked ${r.effective_week}: ${r.scoring_rule_versions_activated} rule, ${r.standard_versions_activated} standard, ${r.category_configs_activated} category-config and ${r.organization_setting_versions_activated} organization-setting version(s) activated.`);
      router.refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Activation failed."); }
    finally { setBusy(false); }
  }
  return <div className="space-y-3"><MutationFeedback error={error} success={success} /><Button variant="secondary" disabled={busy} onClick={() => void activate()}>{busy ? "Checking…" : "Activate due versions"}</Button></div>;
}
