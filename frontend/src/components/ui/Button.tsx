import Link from "next/link";
import { cn } from "@/lib/cn";

const variants = {
  primary: "bg-brand text-white font-extrabold hover:text-white",
  secondary: "bg-fill text-text font-bold hover:text-text",
  text: "bg-transparent text-text-sub font-semibold hover:text-text-sub",
  disabled: "bg-line text-text-sub font-bold cursor-default hover:text-text-sub",
} as const;

export type ButtonVariant = keyof typeof variants;

const base =
  "inline-flex min-h-[56px] items-center justify-center gap-[6px] rounded-control border-0 px-[20px] text-[17px] no-underline cursor-pointer";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant };

export function Button({ variant = "primary", className, type = "button", ...props }: ButtonProps) {
  const disabled = variant === "disabled";
  return (
    <button
      type={type}
      aria-disabled={disabled || undefined}
      className={cn(base, variants[variant], className)}
      {...props}
    />
  );
}

type ButtonLinkProps = React.ComponentProps<typeof Link> & { variant?: ButtonVariant };

export function ButtonLink({ variant = "primary", className, ...props }: ButtonLinkProps) {
  return <Link className={cn(base, variants[variant], className)} {...props} />;
}
