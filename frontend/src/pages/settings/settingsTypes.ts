import type { Dispatch, SetStateAction } from 'react'
import type { SystemSettings } from '@/types'

export type SettingsTab = 'basic' | 'contact' | 'appearance' | 'payment' | 'user' | 'runtime'
export type SetSystemSettings = Dispatch<SetStateAction<SystemSettings | null>>

export type QrcodeType = 'wechat' | 'qq' | 'wechat_official' | 'telegram' | 'reward'
export type QrcodeUrls = Record<QrcodeType, string>
export type QrcodeUploading = Record<QrcodeType, boolean>
