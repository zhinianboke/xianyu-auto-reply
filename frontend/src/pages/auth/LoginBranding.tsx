/** 登录页原有桌面品牌区及移动端页头。 */
import { motion } from 'framer-motion'
import { MessageSquare } from 'lucide-react'
import type { LoginBrandingSettings } from '@/types'

interface BrandingProps { settings: LoginBrandingSettings }

export function LoginBrandingPanel({ settings }: BrandingProps) {
  return (
      <motion.div 
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5 }}
        className="hidden lg:flex lg:w-1/2 bg-slate-900 dark:bg-slate-950 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-transparent" />
        <div className="relative z-10 flex flex-col justify-center px-16">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.5 }}
            className="flex items-center gap-3 mb-8"
          >
            <div className="w-12 h-12 rounded-xl bg-blue-500 flex items-center justify-center">
              <MessageSquare className="w-6 h-6 text-white" />
            </div>
            <span className="text-2xl font-bold text-white">{settings['login.system_name']}</span>
          </motion.div>
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="text-4xl font-bold text-white mb-4 leading-tight whitespace-pre-line"
          >
            {settings['login.system_title']}
          </motion.h1>
          <motion.p 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.5 }}
            className="text-slate-400 text-lg max-w-md"
          >
            {settings['login.system_description']}
          </motion.p>
        </div>
        {/* Decorative circles */}
        <div className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-blue-600/10" />
        <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-blue-600/5" />
      </motion.div>
  )
}

export function LoginMobileBranding({ settings }: BrandingProps) {
  return (
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.4 }}
            className="lg:hidden text-center mb-8"
          >
            <div className="w-12 h-12 rounded-xl bg-blue-500 text-white mx-auto mb-4 flex items-center justify-center">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">{settings['login.system_name']}</h1>
          </motion.div>
  )
}

