import './globals.css'
import { Toaster } from '@/components/ui/toaster'

export const metadata = {
  title: 'NeoNoble Ramp',
  description: 'Embedded Transak on/off-ramp for NENO',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Toaster />
      </body>
    </html>
  )
}
