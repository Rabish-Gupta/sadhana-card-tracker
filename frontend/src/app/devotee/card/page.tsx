import { DailyCardEditor } from "@/components/devotee/daily-card-editor";
import { serverApi } from "@/lib/auth/server";
import type { DailyCardPublic } from "@/lib/api/types";

export default async function TodayCardPage() {
  const card = await serverApi<DailyCardPublic>("/cards/today");
  return <DailyCardEditor initialCard={card} />;
}
