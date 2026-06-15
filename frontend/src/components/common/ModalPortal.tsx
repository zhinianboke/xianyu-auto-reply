import { type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface ModalPortalProps {
  children: ReactNode
  open: boolean
}

export function ModalPortal({ children, open }: ModalPortalProps) {
  if (!open || typeof document === 'undefined') {
    return null
  }

  return createPortal(children, document.body)
}
