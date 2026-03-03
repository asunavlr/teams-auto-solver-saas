import { Sheet, SheetContent } from "@/components/ui/sheet"
import { SidebarContent } from "./sidebar"

interface MobileSidebarProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function MobileSidebar({ open, onOpenChange }: MobileSidebarProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="w-[220px] p-0" showCloseButton={false}>
        <SidebarContent onNavClick={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  )
}
