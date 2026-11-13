import type { DeviceConditions } from "@/features/conditions/types";
import type { ProfileFormData } from "@/features/profile/mocks/profile";

/** 알지 못하는 조건은 판정에 보내지 않아요. */
export function defaultDevice(data: ProfileFormData): DeviceConditions {
  return {
    selectionVersion: 2,
    birth: "",
    regionCode: "",
    searchRegionCodes: [],
    head: "",
    statuses: [],
    marry: "",
    kids: null,
    householdSize: "",
    homelessPeriod: "",
    bankbookPeriod: "",
    paymentCount: "",
    priorities: data.defaultPriorities,
  };
}
