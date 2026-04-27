import { Toaster as SonnerToaster } from "sonner";

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      richColors
      closeButton
      theme="light"
      toastOptions={{
        className:
          "rounded-md border border-border bg-card text-card-foreground shadow-md",
      }}
    />
  );
}
