"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { Suspense, useState } from "react";
import { Analytics } from "@/shared/analytics/Analytics";
import { DemoNotice } from "@/shared/layout/DemoNotice";
import { OfflineBanner } from "@/shared/pwa/OfflineBanner";
import { ServiceHoursBanner } from "@/shared/pwa/ServiceHoursBanner";
import { ServiceWorkerRegister } from "@/shared/pwa/ServiceWorkerRegister";

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
