/**
 * 地址库页面
 *
 * 功能：
 * 1. 「随机地址库」Tab：全局通用地址（管理员维护，发布时回退使用）
 * 2. 「个人地址库」Tab：用户本人维护，发布时优先使用，支持导入导出
 */
import { useState } from 'react'
import { GlobalAddressTab } from './GlobalAddressTab'
import { PersonalAddressTab } from './PersonalAddressTab'

type AddressTab = 'global' | 'personal'

export function PublishAddresses() {
  const [activeTab, setActiveTab] = useState<AddressTab>('global')

  return (
    <div className="space-y-4">
      <div className="page-header">
        <h1 className="page-title">地址库</h1>
      </div>

      {/* Tab 切换 */}
      <div className="flex border-b border-slate-200 dark:border-slate-700">
        <button
          onClick={() => setActiveTab('global')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'global'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          随机地址库
        </button>
        <button
          onClick={() => setActiveTab('personal')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'personal'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          个人地址库
        </button>
      </div>

      {activeTab === 'global' && <GlobalAddressTab />}
      {activeTab === 'personal' && <PersonalAddressTab />}
    </div>
  )
}

export default PublishAddresses
