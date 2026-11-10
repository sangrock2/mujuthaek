"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";
import { Analytics } from "@/components/analytics/Analytics";
import { OfflineBanner } from "@/components/pwa/OfflineBanner";
import { ServiceHoursBanner } from "@/components/pwa/ServiceHoursBanner";
import { ServiceWorkerRegister } from "@/components/pwa/ServiceWorkerRegister";

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
      <Analytics />
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
