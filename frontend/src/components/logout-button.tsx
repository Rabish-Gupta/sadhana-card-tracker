"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

export function LogoutButton() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  return (
    <Button
      variant="secondary"
      disabled={pending}
      onClick={async () => {
        setPending(true);
        await fetch("/api/session/logout", { method: "POST" });
        router.replace("/login");
        router.refresh();
      }}
    >
      {pending ? "Signing out…" : "Logout"}
    </Button>
  );
}
