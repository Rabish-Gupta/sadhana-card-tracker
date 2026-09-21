import { NextResponse } from "next/server";
import { publicAppVersion } from "@/lib/env";

export async function GET() {
  return NextResponse.json({ app: "Sadhana Card Tracker Frontend", version: publicAppVersion(), backend_contract: "v0.11.2" }, { headers: { "cache-control": "no-store" } });
}
