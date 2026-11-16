"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { Suspense, useState } from "react";
import { Analytics } from "@/shared/analytics/Analytics";
import { DemoNotice } from "@/shared/layout/DemoNotice";
import { OfflineBanner } from "@/shared/pwa/OfflineBanner";
import { ServiceHoursBanner } from "@/shared/pwa/ServiceHoursBanner";
import { ServiceWorkerRegister } from "@/shared/pwa/ServiceWorkerRegister";
import { SessionSync } from "@/features/auth/session";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 60 * 1000, retry: 1 },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {/* SessionSync는 주소(usePathname)를 읽어서, 주소가 요청 때 정해지는 화면도 미리 그릴 수 있게 Suspense로 감싸요 */}
      <Suspense fallback={null}>
        <SessionSync />
      </Suspense>
      <ServiceWorkerRegister />
      <OfflineBanner />
      <ServiceHoursBanner />
      <Suspense fallback={null}>
        <Analytics />
      </Suspense>
      <DemoNotice />
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
