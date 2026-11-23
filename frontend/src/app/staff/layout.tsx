import type { Metadata } from "next";

import { StaffShell } from "@/components/staff/StaffShell";

export const metadata: Metadata = {
  title: "Staff console – Ceylon Compass Holidays",
  robots: { index: false, follow: false },
};

/** Staff pages live apart from the traveller chat: own layout, own header, sign-in required. */
export default function StaffLayout({ children }: { children: React.ReactNode }) {
  return <StaffShell>{children}</StaffShell>;
}
